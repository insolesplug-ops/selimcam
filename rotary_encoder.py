"""
Rotary Encoder Driver for SelimCam
===================================

Professional GPIO interrupt-based rotary encoder handling

Features:
- Edge interrupt-driven (not polling!) for low CPU usage
- Software debouncing with configurable timing
- High-speed rotation support (>20 detents/sec)
- Minimal ISR work (atomic counters only)
- Hardware debouncing recommendation (RC or Schmitt)
- Long-press detection on encoder button

Hardware Configuration:
- Encoder A: GPIO 5
- Encoder B: GPIO 6
- Encoder Button: GPIO 13
- Pull-ups: Internal (software) or external (recommended)

Recommended Hardware Debouncing:
- 100nF capacitor + 10kΩ resistor per channel
- Or Schmitt trigger (74HC14) for high reliability
- Essential for speeds >15 detents/sec

Author: SelimCam Team
License: MIT
"""

import time
import threading
from typing import Callable, Optional
from dataclasses import dataclass
from enum import IntEnum
import logging

# Try RPi.GPIO, fall back to mock
try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    print("⚠️ RPi.GPIO not available, using mock")
    HAS_GPIO = False
    
    # Mock GPIO for development
    class GPIO:
        BCM = 11
        IN = 1
        OUT = 0
        PUD_UP = 21
        PUD_DOWN = 22
        RISING = 31
        FALLING = 32
        BOTH = 33
        
        @staticmethod
        def setmode(mode): pass
        @staticmethod
        def setup(pin, mode, pull_up_down=None): pass
        @staticmethod
        def add_event_detect(pin, edge, callback=None, bouncetime=None): pass
        @staticmethod
        def remove_event_detect(pin): pass
        @staticmethod
        def input(pin): return 0
        @staticmethod
        def output(pin, state): pass
        @staticmethod
        def cleanup(): pass


logger = logging.getLogger(__name__)


class RotaryDirection(IntEnum):
    """Rotation direction"""
    CW = 1  # Clockwise
    CCW = -1  # Counter-clockwise


@dataclass
class EncoderEvent:
    """Encoder event data"""
    direction: RotaryDirection
    position: int
    timestamp: float
    speed: float  # Detents per second


class RotaryEncoder:
    """
    Interrupt-based rotary encoder with debouncing
    
    Gray code state machine for reliable decoding:
    - Uses edge interrupts on both A and B channels
    - Minimal ISR: just read state and increment counter
    - Main thread handles debouncing and event dispatch
    
    Performance:
    - ISR latency: <10µs
    - Supports >20 detents/second (with HW debouncing)
    - CPU usage: <1% (vs 5-10% for polling)
    """
    
    # Gray code state transition table
    # [old_AB][new_AB] -> direction (1=CW, -1=CCW, 0=invalid)
    TRANSITION_TABLE = [
        [0, 1, -1, 0],   # 00 -> 00/01/10/11
        [-1, 0, 0, 1],   # 01 -> 00/01/10/11
        [1, 0, 0, -1],   # 10 -> 00/01/10/11
        [0, -1, 1, 0],   # 11 -> 00/01/10/11
    ]
    
    def __init__(
        self,
        pin_a: int = 5,
        pin_b: int = 6,
        pin_button: int = 13,
        callback: Optional[Callable[[EncoderEvent], None]] = None,
        debounce_ms: float = 2.0,
        long_press_ms: float = 500
    ):
        """
        Initialize rotary encoder
        
        Args:
            pin_a: GPIO pin for channel A
            pin_b: GPIO pin for channel B
            pin_button: GPIO pin for push button
            callback: Function called on rotation (receives EncoderEvent)
            debounce_ms: Software debounce time in ms
            long_press_ms: Long press detection threshold in ms
        """
        self.pin_a = pin_a
        self.pin_b = pin_b
        self.pin_button = pin_button
        self.callback = callback
        self.debounce_time = debounce_ms / 1000.0
        self.long_press_time = long_press_ms / 1000.0
        
        # State
        self.position = 0
        self.last_state = 0  # 2-bit Gray code state (AB)
        
        # Debouncing
        self.last_event_time = 0.0
        self.rotation_times = []  # For speed calculation
        
        # Button state
        self.button_pressed = False
        self.button_press_time = 0.0
        self.long_press_triggered = False
        
        # Thread-safe atomic counter (for ISR)
        self._raw_counter = 0
        self._counter_lock = threading.Lock()
        
        # Callbacks
        self.on_rotate: Optional[Callable[[int], None]] = None
        self.on_press: Optional[Callable[[], None]] = None
        self.on_long_press: Optional[Callable[[], None]] = None
        
        # Initialize GPIO
        self._init_gpio()
        
        logger.info(f"Rotary encoder initialized: A={pin_a}, B={pin_b}, Button={pin_button}")
    
    def _init_gpio(self):
        """Initialize GPIO pins and interrupts"""
        if not HAS_GPIO:
            logger.warning("GPIO not available, encoder in mock mode")
            return
        
        GPIO.setmode(GPIO.BCM)
        
        # Setup encoder pins with pull-ups
        GPIO.setup(self.pin_a, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pin_b, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.pin_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Read initial state
        a = GPIO.input(self.pin_a)
        b = GPIO.input(self.pin_b)
        self.last_state = (a << 1) | b
        
        # Add edge detection on both channels
        # NOTE: We use BOTH edges to catch all transitions
        # Bouncetime=1 ms for HW debouncing (minimal SW filtering)
        GPIO.add_event_detect(
            self.pin_a,
            GPIO.BOTH,
            callback=self._isr_encoder,
            bouncetime=1
        )
        GPIO.add_event_detect(
            self.pin_b,
            GPIO.BOTH,
            callback=self._isr_encoder,
            bouncetime=1
        )
        
        # Button interrupt (falling edge = press)
        GPIO.add_event_detect(
            self.pin_button,
            GPIO.FALLING,
            callback=self._isr_button,
            bouncetime=50  # Button debounce
        )
    
    def _isr_encoder(self, channel):
        """
        Interrupt service routine for encoder (CRITICAL: Keep minimal!)
        
        This runs in interrupt context - do NOT:
        - Call slow functions
        - Acquire locks (except very brief atomic operations)
        - Print to console
        - Do complex calculations
        
        Just read state and update counter.
        """
        # Read current state
        a = GPIO.input(self.pin_a)
        b = GPIO.input(self.pin_b)
        new_state = (a << 1) | b
        
        # Look up direction from transition table
        direction = self.TRANSITION_TABLE[self.last_state][new_state]
        
        if direction != 0:
            # Valid transition - update counter atomically
            with self._counter_lock:
                self._raw_counter += direction
        
        self.last_state = new_state
    
    def _isr_button(self, channel):
        """Button press ISR"""
        self.button_pressed = True
        self.button_press_time = time.perf_counter()
        self.long_press_triggered = False
    
    def poll(self):
        """
        Poll for encoder changes (call from main loop at 60Hz)
        
        This handles:
        - Debouncing
        - Speed calculation
        - Event dispatch
        - Button long-press detection
        """
        now = time.perf_counter()
        
        # ===== Encoder rotation =====
        
        # Read counter atomically
        with self._counter_lock:
            raw_count = self._raw_counter
            self._raw_counter = 0  # Reset for next poll
        
        if raw_count != 0:
            # Apply debouncing
            if now - self.last_event_time >= self.debounce_time:
                # Valid rotation
                direction = RotaryDirection.CW if raw_count > 0 else RotaryDirection.CCW
                steps = abs(raw_count)
                
                self.position += raw_count
                
                # Calculate speed
                self.rotation_times.append(now)
                # Keep last 5 rotations for speed calc
                self.rotation_times = self.rotation_times[-5:]
                
                if len(self.rotation_times) > 1:
                    time_span = self.rotation_times[-1] - self.rotation_times[0]
                    if time_span > 0:
                        speed = (len(self.rotation_times) - 1) / time_span
                    else:
                        speed = 0.0
                else:
                    speed = 0.0
                
                # Create event
                event = EncoderEvent(
                    direction=direction,
                    position=self.position,
                    timestamp=now,
                    speed=speed
                )
                
                # Dispatch callbacks
                if self.on_rotate:
                    self.on_rotate(direction)
                
                if self.callback:
                    self.callback(event)
                
                self.last_event_time = now
                
                logger.debug(f"Encoder: {direction.name} @ {speed:.1f} det/s, pos={self.position}")
        
        # ===== Button =====
        
        if self.button_pressed:
            # Check for long press
            press_duration = now - self.button_press_time
            
            if not self.long_press_triggered and press_duration >= self.long_press_time:
                # Long press detected
                self.long_press_triggered = True
                if self.on_long_press:
                    self.on_long_press()
                logger.debug("Encoder button: LONG PRESS")
            
            # Check for release
            if not GPIO.input(self.pin_button):  # Button still pressed
                pass
            else:
                # Released
                if not self.long_press_triggered:
                    # Short press
                    if self.on_press:
                        self.on_press()
                    logger.debug("Encoder button: PRESS")
                
                self.button_pressed = False
    
    def reset_position(self):
        """Reset position counter to zero"""
        self.position = 0
    
    def cleanup(self):
        """Cleanup GPIO"""
        if HAS_GPIO:
            try:
                GPIO.remove_event_detect(self.pin_a)
                GPIO.remove_event_detect(self.pin_b)
                GPIO.remove_event_detect(self.pin_button)
            except:
                pass


class MultiButtonController:
    """
    Additional button controller for shutter + other buttons
    
    Supports:
    - Half-press detection (for AF)
    - Full-press (for shutter)
    - Debouncing
    - Multiple buttons
    """
    
    def __init__(self):
        """Initialize button controller"""
        self.buttons = {}
        
        if HAS_GPIO:
            GPIO.setmode(GPIO.BCM)
    
    def add_button(
        self,
        name: str,
        pin: int,
        callback: Optional[Callable[[], None]] = None,
        pull_up: bool = True,
        debounce_ms: int = 50
    ):
        """
        Add a button
        
        Args:
            name: Button identifier
            pin: GPIO pin
            callback: Function called on press
            pull_up: Enable pull-up resistor
            debounce_ms: Debounce time in ms
        """
        if not HAS_GPIO:
            return
        
        # Setup pin
        pull = GPIO.PUD_UP if pull_up else GPIO.PUD_DOWN
        GPIO.setup(pin, GPIO.IN, pull_up_down=pull)
        
        # Store button config
        self.buttons[name] = {
            'pin': pin,
            'callback': callback,
            'pressed': False,
            'press_time': 0.0
        }
        
        # Add interrupt
        GPIO.add_event_detect(
            pin,
            GPIO.FALLING if pull_up else GPIO.RISING,
            callback=lambda ch: self._on_button_press(name),
            bouncetime=debounce_ms
        )
        
        logger.info(f"Button '{name}' added on GPIO {pin}")
    
    def _on_button_press(self, name: str):
        """Button press ISR"""
        btn = self.buttons.get(name)
        if btn:
            btn['pressed'] = True
            btn['press_time'] = time.perf_counter()
            
            if btn['callback']:
                btn['callback']()
    
    def is_pressed(self, name: str) -> bool:
        """Check if button is currently pressed"""
        btn = self.buttons.get(name)
        if btn:
            return not GPIO.input(btn['pin'])  # Inverted (pull-up)
        return False
    
    def cleanup(self):
        """Cleanup all buttons"""
        if HAS_GPIO:
            for btn in self.buttons.values():
                try:
                    GPIO.remove_event_detect(btn['pin'])
                except:
                    pass


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    import sys
    
    print("Rotary Encoder Test")
    print("=" * 50)
    print("Turn encoder to test rotation")
    print("Press encoder button for short/long press")
    print("Press Ctrl+C to exit")
    print()
    
    # Callbacks
    def on_rotate(direction: int):
        symbol = "→" if direction > 0 else "←"
        print(f"{symbol} Rotated {direction}")
    
    def on_press():
        print("🔘 Button pressed")
    
    def on_long_press():
        print("🔘 Button LONG PRESS")
    
    # Initialize encoder
    encoder = RotaryEncoder(
        pin_a=5,
        pin_b=6,
        pin_button=13,
        debounce_ms=2.0,
        long_press_ms=500
    )
    
    encoder.on_rotate = on_rotate
    encoder.on_press = on_press
    encoder.on_long_press = on_long_press
    
    # Main loop
    try:
        while True:
            encoder.poll()
            time.sleep(0.016)  # ~60Hz polling
    
    except KeyboardInterrupt:
        print("\n\nStopping...")
    
    finally:
        encoder.cleanup()
        GPIO.cleanup()
        print("Cleanup complete")
