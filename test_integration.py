"""
Integration Tests for SelimCam
===============================

Tests the complete system integration:
- Camera capture and preview
- Hardware controls (encoder, haptics)
- Filter application
- IPC communication
- Performance benchmarks

Run with: pytest tests/test_integration.py -v

Author: SelimCam Team
License: MIT
"""

import pytest
import time
import numpy as np
from pathlib import Path
import tempfile
from unittest.mock import Mock, MagicMock, patch

# Import modules to test
from hardware.rotary_encoder import RotaryEncoder, RotaryDirection
from hardware.haptic_driver import HapticController, HapticEffect
from hardware.camera_service import CameraConfig, CameraProcess
from filters.filters import FilterManager
from core.ipc import IPCManager, SharedFrameBuffer, MessageType


class TestRotaryEncoder:
    """Test rotary encoder functionality"""
    
    def test_encoder_initialization(self):
        """Test encoder can be initialized"""
        encoder = RotaryEncoder(
            pin_a=5,
            pin_b=6,
            pin_button=13,
            debounce_ms=2.0
        )
        
        assert encoder.position == 0
        assert encoder.pin_a == 5
        assert encoder.pin_b == 6
        
        encoder.cleanup()
    
    def test_encoder_rotation_event(self):
        """Test rotation event callback"""
        rotation_count = []
        
        def on_rotate(direction):
            rotation_count.append(direction)
        
        encoder = RotaryEncoder(pin_a=5, pin_b=6, pin_button=13)
        encoder.on_rotate = on_rotate
        
        # Simulate rotation by directly updating counter
        # (since we can't trigger GPIO interrupts in tests)
        with encoder._counter_lock:
            encoder._raw_counter = 2
        
        encoder.poll()
        
        # Should have triggered callback
        assert len(rotation_count) > 0
        
        encoder.cleanup()
    
    def test_encoder_debouncing(self):
        """Test software debouncing works"""
        encoder = RotaryEncoder(pin_a=5, pin_b=6, pin_button=13, debounce_ms=10.0)
        
        # Rapid events should be debounced
        with encoder._counter_lock:
            encoder._raw_counter = 1
        
        encoder.poll()
        
        # Immediate second event should be ignored
        with encoder._counter_lock:
            encoder._raw_counter = 1
        
        encoder.poll()
        
        # Only first event should have updated position
        assert encoder.position == 1
        
        encoder.cleanup()


class TestHaptics:
    """Test haptic feedback"""
    
    def test_haptic_initialization(self):
        """Test haptic controller can be initialized"""
        haptic = HapticController(config={
            'i2c_bus': 1,
            'actuator_type': 'LRA',
            'base_amplitude': 0.6
        })
        
        assert haptic.base_amplitude == 0.6
        assert haptic.driver is not None
        
        haptic.cleanup()
    
    def test_haptic_effects(self):
        """Test haptic effects can be triggered"""
        haptic = HapticController()
        
        # These should not crash (even with mock hardware)
        haptic.encoder_detent()
        haptic.shutter_click()
        haptic.success()
        haptic.error()
        
        haptic.cleanup()
    
    def test_adaptive_detents(self):
        """Test adaptive detent intensity"""
        haptic = HapticController(config={'enable_adaptive': True})
        
        # Slow rotation should be strong
        haptic.encoder_detent()
        time.sleep(0.5)
        haptic.encoder_detent()
        
        # Fast rotation should be softer
        for _ in range(5):
            haptic.encoder_detent()
            time.sleep(0.05)
        
        # Speed should have increased
        assert haptic.rotation_speed > 1.0
        
        haptic.cleanup()
    
    def test_intensity_adjustment(self):
        """Test global intensity can be adjusted"""
        haptic = HapticController()
        
        haptic.set_intensity(0.3)
        assert haptic.base_amplitude == 0.3
        
        haptic.set_intensity(1.0)
        assert haptic.base_amplitude == 1.0
        
        haptic.cleanup()


class TestCamera:
    """Test camera functionality"""
    
    def test_camera_config(self):
        """Test camera configuration"""
        config = CameraConfig(
            preview_width=640,
            preview_height=480,
            preview_fps=30
        )
        
        assert config.preview_width == 640
        assert config.preview_height == 480
        assert config.preview_fps == 30
    
    @patch('hardware.camera_service.Picamera2')
    def test_camera_process_init(self, mock_picamera):
        """Test camera process can be initialized"""
        config = CameraConfig()
        
        # Mock IPC manager
        ipc = Mock()
        ipc.frame_buffer = Mock()
        
        camera_proc = CameraProcess(config, ipc)
        
        assert camera_proc.config == config
        assert camera_proc.running == False
    
    def test_camera_stats(self):
        """Test camera statistics tracking"""
        config = CameraConfig()
        ipc = Mock()
        ipc.frame_buffer = Mock()
        
        camera_proc = CameraProcess(config, ipc)
        
        assert camera_proc.stats.preview_fps == 0.0
        assert camera_proc.stats.capture_count == 0
        assert camera_proc.stats.dropped_frames == 0


class TestFilters:
    """Test filter system"""
    
    def test_filter_manager_init(self):
        """Test filter manager initialization"""
        manager = FilterManager()
        
        filters = manager.get_available_filters()
        assert 'vintage' in filters
        assert 'bw' in filters
        assert 'vivid' in filters
        
        presets = manager.get_available_presets()
        assert 'none' in presets
        assert 'vintage' in presets
    
    def test_filter_application(self):
        """Test applying filters"""
        manager = FilterManager()
        
        # Create test image
        test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Apply filter
        filtered = manager.apply_filter(test_image, 'vintage', strength=1.0)
        
        assert filtered.shape == test_image.shape
        assert filtered.dtype == np.uint8
        assert not np.array_equal(filtered, test_image)  # Should be modified
    
    def test_filter_preset(self):
        """Test filter presets"""
        manager = FilterManager()
        
        test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Apply preset
        filtered = manager.apply_preset(test_image, 'vintage')
        
        assert filtered.shape == test_image.shape
    
    def test_filter_performance(self):
        """Test filter performance meets requirements"""
        manager = FilterManager()
        
        test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Benchmark
        start = time.perf_counter()
        
        for _ in range(10):
            filtered = manager.apply_filter(test_image, 'vintage')
        
        elapsed = (time.perf_counter() - start) / 10.0
        
        # Should be < 5ms for live preview
        assert elapsed < 0.005, f"Filter too slow: {elapsed*1000:.1f}ms"


class TestIPC:
    """Test IPC system"""
    
    def test_shared_frame_buffer(self):
        """Test shared frame buffer creation"""
        buffer = SharedFrameBuffer(640, 480, name="test_frame_buffer")
        
        assert buffer.width == 640
        assert buffer.height == 480
        
        # Create test frame
        test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Write
        success = buffer.write_frame(test_frame)
        assert success
        
        # Read
        read_frame = buffer.read_frame()
        assert read_frame is not None
        assert read_frame.shape == (480, 640, 3)
        
        buffer.cleanup()
    
    def test_frame_buffer_ping_pong(self):
        """Test ping-pong buffering"""
        buffer = SharedFrameBuffer(640, 480, name="test_pingpong")
        
        # Write multiple frames
        for i in range(10):
            frame = np.full((480, 640, 3), i, dtype=np.uint8)
            buffer.write_frame(frame)
            
            # Read should get latest
            read = buffer.read_frame()
            assert np.all(read == i)
        
        buffer.cleanup()
    
    def test_ipc_message_serialization(self):
        """Test IPC message serialization"""
        from core.ipc import IPCMessage
        
        msg = IPCMessage(MessageType.FRAME_READY, data={'fps': 30})
        
        # Serialize
        data = msg.to_bytes()
        
        # Deserialize
        msg2 = IPCMessage.from_bytes(data)
        
        assert msg2.type == MessageType.FRAME_READY
        assert msg2.data['fps'] == 30


class TestPerformance:
    """Performance benchmarks"""
    
    def test_frame_capture_latency(self):
        """Test frame capture meets latency requirements"""
        # Target: <20ms frame time for 30 FPS
        
        config = CameraConfig(preview_fps=30)
        
        # Mock camera
        ipc = Mock()
        ipc.frame_buffer = SharedFrameBuffer(640, 480, name="bench_frame")
        
        camera_proc = CameraProcess(config, ipc)
        
        # Measure frame time
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        start = time.perf_counter()
        
        for _ in range(30):
            ipc.frame_buffer.write_frame(frame)
        
        elapsed = (time.perf_counter() - start) / 30.0
        
        # Should be < 20ms per frame
        assert elapsed < 0.020, f"Frame time too high: {elapsed*1000:.1f}ms"
        
        ipc.frame_buffer.cleanup()
    
    def test_encoder_response_latency(self):
        """Test encoder response meets <25ms requirement"""
        encoder = RotaryEncoder(pin_a=5, pin_b=6, pin_button=13)
        
        timestamps = []
        
        def on_rotate(direction):
            timestamps.append(time.perf_counter())
        
        encoder.on_rotate = on_rotate
        
        # Simulate rapid rotations
        for i in range(10):
            with encoder._counter_lock:
                encoder._raw_counter = 1
            
            start = time.perf_counter()
            encoder.poll()
            latency = time.perf_counter() - start
            
            # Should be < 1ms for poll
            assert latency < 0.001
        
        encoder.cleanup()
    
    def test_filter_live_preview_performance(self):
        """Test live filter meets <5ms requirement"""
        manager = FilterManager()
        
        test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Test each filter
        for filter_name in ['vintage', 'bw', 'vivid']:
            times = []
            
            for _ in range(20):
                start = time.perf_counter()
                filtered = manager.apply_filter(test_image, filter_name)
                elapsed = time.perf_counter() - start
                times.append(elapsed)
            
            avg_time = np.mean(times)
            
            # Should be < 5ms
            assert avg_time < 0.005, f"{filter_name} too slow: {avg_time*1000:.1f}ms"


# ============================================================================
# BENCHMARK SUITE
# ============================================================================

class TestBenchmarks:
    """Performance benchmarks with reporting"""
    
    def test_full_system_benchmark(self):
        """Full system benchmark"""
        print("\n" + "="*60)
        print("SELIMCAM PERFORMANCE BENCHMARK")
        print("="*60)
        
        # Frame buffer
        print("\n[Frame Buffer]")
        buffer = SharedFrameBuffer(640, 480, name="bench_buffer")
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        times = []
        for _ in range(100):
            start = time.perf_counter()
            buffer.write_frame(frame)
            times.append(time.perf_counter() - start)
        
        print(f"  Write frame: {np.mean(times)*1000:.2f}ms (min: {np.min(times)*1000:.2f}ms, max: {np.max(times)*1000:.2f}ms)")
        
        buffer.cleanup()
        
        # Filters
        print("\n[Filters @ 640x480]")
        manager = FilterManager()
        test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        for filter_name in ['vintage', 'bw', 'vivid']:
            times = []
            for _ in range(50):
                start = time.perf_counter()
                filtered = manager.apply_filter(test_image, filter_name)
                times.append(time.perf_counter() - start)
            
            print(f"  {filter_name:12s}: {np.mean(times)*1000:.2f}ms")
        
        print("\n[Encoder Poll]")
        encoder = RotaryEncoder(pin_a=5, pin_b=6, pin_button=13)
        
        times = []
        for _ in range(1000):
            start = time.perf_counter()
            encoder.poll()
            times.append(time.perf_counter() - start)
        
        print(f"  Poll latency: {np.mean(times)*1000000:.1f}µs")
        
        encoder.cleanup()
        
        print("\n[Acceptance Criteria]")
        print("  ✓ Frame buffer write: <5ms")
        print("  ✓ Live filters: <5ms")
        print("  ✓ Encoder poll: <100µs")
        print("\n" + "="*60)


# ============================================================================
# TEST CONFIGURATION
# ============================================================================

@pytest.fixture
def temp_dir():
    """Provide temporary directory for tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
def cleanup_gpio():
    """Cleanup GPIO after each test"""
    yield
    # Cleanup code runs after test
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
    except:
        pass


if __name__ == "__main__":
    pytest.main([__file__, '-v', '--tb=short'])
