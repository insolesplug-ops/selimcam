"""
IPC System for Multi-Process Communication
==========================================

Provides:
- ZeroMQ-based messaging between processes
- Shared memory for zero-copy frame transfer
- Event queue for hardware events
- Thread-safe, non-blocking operations

Process Architecture:
1. Camera Process: Capture + encoding
2. UI Process: Rendering + user interaction
3. Hardware Process: GPIO/I2C + haptics

Author: SelimCam Team
License: MIT
"""

import zmq
import time
import multiprocessing as mp
from multiprocessing import shared_memory
from typing import Optional, Any, Dict, Callable
from dataclasses import dataclass, asdict
from enum import Enum, auto
import pickle
import numpy as np
from queue import Empty


class MessageType(Enum):
    """IPC message types"""
    # Camera -> UI
    FRAME_READY = auto()
    CAPTURE_COMPLETE = auto()
    CAMERA_ERROR = auto()
    CAMERA_STATS = auto()
    
    # UI -> Camera
    START_PREVIEW = auto()
    STOP_PREVIEW = auto()
    CAPTURE_PHOTO = auto()
    CAPTURE_VIDEO_START = auto()
    CAPTURE_VIDEO_STOP = auto()
    SET_ZOOM = auto()
    SET_EXPOSURE = auto()
    APPLY_FILTER = auto()
    
    # Hardware -> UI
    ENCODER_EVENT = auto()
    BUTTON_EVENT = auto()
    SENSOR_DATA = auto()
    
    # UI -> Hardware
    HAPTIC_TRIGGER = auto()
    FLASH_TRIGGER = auto()
    
    # Control
    SHUTDOWN = auto()
    PING = auto()
    PONG = auto()


@dataclass
class IPCMessage:
    """Structured IPC message"""
    type: MessageType
    data: Any = None
    timestamp: float = 0.0
    source: str = ""
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.perf_counter()
    
    def to_bytes(self) -> bytes:
        """Serialize to bytes"""
        return pickle.dumps(asdict(self))
    
    @staticmethod
    def from_bytes(data: bytes) -> 'IPCMessage':
        """Deserialize from bytes"""
        d = pickle.loads(data)
        d['type'] = MessageType(d['type'])
        return IPCMessage(**d)


class SharedFrameBuffer:
    """
    Zero-copy frame buffer using shared memory
    
    Design:
    - Fixed-size buffer for preview frames
    - Ping-pong buffering (2 buffers)
    - Lock-free reading (atomic buffer swapping)
    - Camera writes, UI reads
    
    Memory layout:
    [width][height][current_buffer_idx][buffer_A][buffer_B]
    """
    
    def __init__(self, width: int, height: int, name: str = "selimcam_frame"):
        self.width = width
        self.height = height
        self.channels = 3  # RGB
        self.frame_size = width * height * self.channels
        
        # Total size: metadata + 2 buffers
        # [4 bytes width][4 bytes height][4 bytes idx][buffer_A][buffer_B]
        metadata_size = 12  # 3 int32s
        total_size = metadata_size + (self.frame_size * 2)
        
        # Create or attach to shared memory
        try:
            self.shm = shared_memory.SharedMemory(name=name, create=True, size=total_size)
            self.is_owner = True
            # Initialize metadata
            self._write_metadata(width, height, 0)
        except FileExistsError:
            self.shm = shared_memory.SharedMemory(name=name, create=False)
            self.is_owner = False
        
        self.name = name
        self.metadata_size = metadata_size
        
        # Create numpy views
        self._setup_buffers()
    
    def _setup_buffers(self):
        """Setup numpy buffer views"""
        # Metadata view
        self.metadata = np.ndarray(
            (3,), dtype=np.int32, buffer=self.shm.buf, offset=0
        )
        
        # Buffer A
        offset_a = self.metadata_size
        self.buffer_a = np.ndarray(
            (self.height, self.width, self.channels),
            dtype=np.uint8,
            buffer=self.shm.buf,
            offset=offset_a
        )
        
        # Buffer B
        offset_b = self.metadata_size + self.frame_size
        self.buffer_b = np.ndarray(
            (self.height, self.width, self.channels),
            dtype=np.uint8,
            buffer=self.shm.buf,
            offset=offset_b
        )
    
    def _write_metadata(self, width: int, height: int, current_idx: int):
        """Write metadata (width, height, current buffer index)"""
        meta = np.ndarray((3,), dtype=np.int32, buffer=self.shm.buf, offset=0)
        meta[0] = width
        meta[1] = height
        meta[2] = current_idx
    
    def write_frame(self, frame: np.ndarray) -> bool:
        """
        Write frame to inactive buffer and swap (writer only)
        
        Args:
            frame: RGB frame (height, width, 3)
        
        Returns:
            True if successful
        """
        if frame.shape != (self.height, self.width, self.channels):
            return False
        
        # Get current active buffer
        current_idx = int(self.metadata[2])
        
        # Write to inactive buffer
        if current_idx == 0:
            np.copyto(self.buffer_b, frame)
            new_idx = 1
        else:
            np.copyto(self.buffer_a, frame)
            new_idx = 0
        
        # Atomic swap
        self.metadata[2] = new_idx
        
        return True
    
    def read_frame(self) -> Optional[np.ndarray]:
        """
        Read current active frame (reader only)
        
        Returns:
            View of current frame (DO NOT MODIFY!)
        """
        current_idx = int(self.metadata[2])
        
        if current_idx == 0:
            return self.buffer_a
        else:
            return self.buffer_b
    
    def cleanup(self):
        """Cleanup shared memory"""
        if self.is_owner:
            self.shm.close()
            self.shm.unlink()
        else:
            self.shm.close()


class ZMQChannel:
    """
    ZeroMQ-based IPC channel
    
    Patterns:
    - PUB/SUB for broadcasts (camera frames ready)
    - REQ/REP for commands (capture photo)
    - PUSH/PULL for events (hardware events)
    """
    
    def __init__(self, role: str, pattern: str, endpoint: str):
        """
        Initialize ZMQ channel
        
        Args:
            role: 'publisher', 'subscriber', 'server', 'client', 'pusher', 'puller'
            pattern: 'pubsub', 'reqrep', 'pushpull'
            endpoint: e.g. 'tcp://127.0.0.1:5555' or 'ipc:///tmp/selimcam.sock'
        """
        self.role = role
        self.pattern = pattern
        self.endpoint = endpoint
        
        self.context = zmq.Context()
        
        # Create socket based on role
        if role == 'publisher':
            self.socket = self.context.socket(zmq.PUB)
            self.socket.bind(endpoint)
        elif role == 'subscriber':
            self.socket = self.context.socket(zmq.SUB)
            self.socket.connect(endpoint)
            self.socket.setsockopt(zmq.SUBSCRIBE, b'')  # Subscribe to all
        elif role == 'server':
            self.socket = self.context.socket(zmq.REP)
            self.socket.bind(endpoint)
        elif role == 'client':
            self.socket = self.context.socket(zmq.REQ)
            self.socket.connect(endpoint)
        elif role == 'pusher':
            self.socket = self.context.socket(zmq.PUSH)
            self.socket.bind(endpoint)
        elif role == 'puller':
            self.socket = self.context.socket(zmq.PULL)
            self.socket.connect(endpoint)
        
        # Non-blocking by default
        self.socket.setsockopt(zmq.RCVTIMEO, 0)
    
    def send(self, message: IPCMessage):
        """Send message"""
        try:
            self.socket.send(message.to_bytes())
        except zmq.Again:
            pass  # Non-blocking send failed
    
    def recv(self) -> Optional[IPCMessage]:
        """Receive message (non-blocking)"""
        try:
            data = self.socket.recv()
            return IPCMessage.from_bytes(data)
        except zmq.Again:
            return None
    
    def cleanup(self):
        """Cleanup"""
        self.socket.close()
        self.context.term()


class EventQueue:
    """
    Thread-safe event queue for hardware events
    
    Uses multiprocessing.Queue for IPC
    """
    
    def __init__(self, maxsize: int = 1000):
        self.queue = mp.Queue(maxsize=maxsize)
    
    def put(self, event_type: str, data: Any = None, block: bool = False):
        """Put event in queue"""
        try:
            self.queue.put(
                {'type': event_type, 'data': data, 'timestamp': time.perf_counter()},
                block=block
            )
        except:
            pass  # Queue full
    
    def get(self, timeout: float = 0.0) -> Optional[Dict]:
        """Get event from queue (non-blocking by default)"""
        try:
            return self.queue.get(timeout=timeout)
        except Empty:
            return None
    
    def get_all(self) -> list:
        """Get all pending events"""
        events = []
        while True:
            event = self.get()
            if event is None:
                break
            events.append(event)
        return events


class IPCManager:
    """
    Central IPC manager
    
    Sets up all communication channels:
    - Camera -> UI: Frame notifications (PUB/SUB)
    - UI -> Camera: Commands (REQ/REP)
    - Hardware -> UI: Events (PUSH/PULL)
    - UI -> Hardware: Control (REQ/REP)
    """
    
    def __init__(self, role: str):
        """
        Initialize IPC manager
        
        Args:
            role: 'camera', 'ui', 'hardware'
        """
        self.role = role
        
        # Shared frame buffer
        if role == 'camera':
            self.frame_buffer = SharedFrameBuffer(640, 480, name="selimcam_frame")
        else:
            time.sleep(0.1)  # Wait for camera to create buffer
            self.frame_buffer = SharedFrameBuffer(640, 480, name="selimcam_frame")
        
        # ZMQ channels
        self.channels: Dict[str, ZMQChannel] = {}
        
        # Setup channels based on role
        if role == 'camera':
            self.channels['frame_pub'] = ZMQChannel(
                'publisher', 'pubsub', 'tcp://127.0.0.1:5555'
            )
            self.channels['command_server'] = ZMQChannel(
                'server', 'reqrep', 'tcp://127.0.0.1:5556'
            )
        
        elif role == 'ui':
            self.channels['frame_sub'] = ZMQChannel(
                'subscriber', 'pubsub', 'tcp://127.0.0.1:5555'
            )
            self.channels['command_client'] = ZMQChannel(
                'client', 'reqrep', 'tcp://127.0.0.1:5556'
            )
            self.channels['hw_events'] = ZMQChannel(
                'puller', 'pushpull', 'tcp://127.0.0.1:5557'
            )
            self.channels['hw_control'] = ZMQChannel(
                'client', 'reqrep', 'tcp://127.0.0.1:5558'
            )
        
        elif role == 'hardware':
            self.channels['event_pusher'] = ZMQChannel(
                'pusher', 'pushpull', 'tcp://127.0.0.1:5557'
            )
            self.channels['control_server'] = ZMQChannel(
                'server', 'reqrep', 'tcp://127.0.0.1:5558'
            )
        
        # Event queue (for hardware)
        self.event_queue = EventQueue() if role == 'hardware' else None
    
    def send_frame_ready(self):
        """Notify that new frame is ready (camera only)"""
        if 'frame_pub' in self.channels:
            self.channels['frame_pub'].send(
                IPCMessage(MessageType.FRAME_READY, source='camera')
            )
    
    def send_command(self, msg_type: MessageType, data: Any = None) -> Optional[IPCMessage]:
        """Send command to camera (ui only)"""
        if 'command_client' in self.channels:
            self.channels['command_client'].send(
                IPCMessage(msg_type, data, source='ui')
            )
            # Wait for response
            time.sleep(0.001)
            return self.channels['command_client'].recv()
        return None
    
    def send_hw_event(self, event_type: str, data: Any = None):
        """Send hardware event to UI (hardware only)"""
        if 'event_pusher' in self.channels:
            self.channels['event_pusher'].send(
                IPCMessage(MessageType.ENCODER_EVENT, {'type': event_type, 'data': data}, source='hardware')
            )
    
    def poll_hw_events(self) -> list:
        """Poll hardware events (ui only)"""
        if 'hw_events' not in self.channels:
            return []
        
        events = []
        while True:
            msg = self.channels['hw_events'].recv()
            if msg is None:
                break
            events.append(msg)
        return events
    
    def cleanup(self):
        """Cleanup all channels"""
        for channel in self.channels.values():
            channel.cleanup()
        
        if self.frame_buffer:
            self.frame_buffer.cleanup()


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # Example: Camera process
    def camera_process():
        ipc = IPCManager('camera')
        
        # Simulate frame capture
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        for i in range(10):
            # Write frame
            ipc.frame_buffer.write_frame(frame)
            
            # Notify UI
            ipc.send_frame_ready()
            
            time.sleep(0.033)  # 30 FPS
        
        ipc.cleanup()
    
    # Example: UI process
    def ui_process():
        time.sleep(0.2)  # Wait for camera setup
        ipc = IPCManager('ui')
        
        for i in range(10):
            # Read frame
            frame = ipc.frame_buffer.read_frame()
            if frame is not None:
                print(f"UI: Received frame shape: {frame.shape}, mean: {frame.mean():.1f}")
            
            time.sleep(0.033)
        
        ipc.cleanup()
    
    # Run test
    import multiprocessing as mp
    
    p_camera = mp.Process(target=camera_process)
    p_ui = mp.Process(target=ui_process)
    
    p_camera.start()
    p_ui.start()
    
    p_camera.join()
    p_ui.join()
    
    print("IPC test complete!")
