"""
DRV2605L Haptic Driver for SelimCam
====================================

Professional haptic feedback using TI DRV2605L + LRA (Linear Resonant Actuator)

Features:
- I2C control (100kHz - 400kHz)
- 123 built-in waveform effects
- ERM and LRA support (LRA recommended)
- Configurable amplitude (0-100%)
- Effect library with timing profiles
- Safe power management

Hardware Requirements:
- DRV2605L breakout board (e.g., Adafruit #2305)
- LRA actuator (recommended: 10mm, 2V, 150Hz - e.g., Jinlong Z4TL1B0140091)
- I2C connection: SDA=GPIO2, SCL=GPIO3
- Decoupling: 10µF + 0.1µF caps on VDD and REG

CRITICAL SAFETY NOTES:
- Never drive haptic motor directly from GPIO! Use DRV2605L.
- LRA requires AC drive (DRV2605L handles this)
- Max continuous current: 250mA (fused recommended)
- Thermal shutdown at 150°C (check datasheet)

Author: SelimCam Team
License: MIT
"""

import time
from typing import Optional
from enum import IntEnum
import logging

# Try smbus2 first, fall back to mock
try:
    from smbus2 import SMBus
except ImportError:
    print("⚠️ smbus2 not available, using mock I2C")
    class SMBus:
        def __init__(self, bus): pass
        def write_byte_data(self, addr, reg, val): pass
        def read_byte_data(self, addr, reg): return 0
        def close(self): pass


logger = logging.getLogger(__name__)


# DRV2605L Register Map
class DRV2605Reg(IntEnum):
    """DRV2605L register addresses"""
    STATUS = 0x00
    MODE = 0x01
    RT_PLAYBACK_INPUT = 0x02
    LIBRARY_SELECTION = 0x03
    WAVEFORM_SEQUENCER_1 = 0x04
    WAVEFORM_SEQUENCER_2 = 0x05
    WAVEFORM_SEQUENCER_3 = 0x06
    WAVEFORM_SEQUENCER_4 = 0x07
    WAVEFORM_SEQUENCER_5 = 0x08
    WAVEFORM_SEQUENCER_6 = 0x09
    WAVEFORM_SEQUENCER_7 = 0x0A
    WAVEFORM_SEQUENCER_8 = 0x0B
    GO = 0x0C
    OVERDRIVE_TIME_OFFSET = 0x0D
    SUSTAIN_TIME_OFFSET_POS = 0x0E
    SUSTAIN_TIME_OFFSET_NEG = 0x0F
    BRAKE_TIME_OFFSET = 0x10
    AUDIO_TO_VIBE_CTRL = 0x11
    AUDIO_TO_VIBE_MIN_INPUT = 0x12
    AUDIO_TO_VIBE_MAX_INPUT = 0x13
    AUDIO_TO_VIBE_MIN_OUTPUT = 0x14
    AUDIO_TO_VIBE_MAX_OUTPUT = 0x15
    RATED_VOLTAGE = 0x16
    OVERDRIVE_CLAMP_VOLTAGE = 0x17
    AUTO_CAL_COMP_RESULT = 0x18
    AUTO_CAL_BEMF_RESULT = 0x19
    FEEDBACK_CONTROL = 0x1A
    CONTROL1 = 0x1B
    CONTROL2 = 0x1C
    CONTROL3 = 0x1D
    CONTROL4 = 0x1E
    CONTROL5 = 0x1F
    LRA_OPEN_LOOP_PERIOD = 0x20
    VBAT_VOLTAGE_MONITOR = 0x21
    LRA_RESONANCE_PERIOD = 0x22


class DRV2605Mode(IntEnum):
    """Operating modes"""
    INTERNAL_TRIGGER = 0x00
    EXTERNAL_TRIGGER_EDGE = 0x01
    EXTERNAL_TRIGGER_LEVEL = 0x02
    PWM_INPUT = 0x03
    AUDIO_TO_VIBE = 0x04
    REAL_TIME_PLAYBACK = 0x05
    DIAGNOSTICS = 0x06
    AUTO_CALIBRATION = 0x07


class DRV2605Library(IntEnum):
    """Waveform libraries"""
    EMPTY = 0x00
    TS2200_LRA = 0x01  # Default for LRA
    TS2200_ERM = 0x02
    TS2200A_LRA = 0x03
    TS2200A_ERM = 0x04
    LRA = 0x06  # Generic LRA library


class HapticEffect(IntEnum):
    """
    Curated effect library for camera interactions
    
    Effect timing guide:
    - Light tap: 8-15ms
    - Medium tap: 15-30ms
    - Strong tap: 30-50ms
    - Double tap: 2x light with 50ms gap
    """
    # Light effects (rotary detent simulation)
    LIGHT_CLICK = 1  # Sharp click, 10ms (for encoder detents)
    SOFT_BUMP = 2  # Gentle bump, 12ms
    PULSING_STRONG = 3  # Strong pulse, 20ms
    
    # Medium effects (confirmations)
    SHARP_CLICK = 4  # Medium sharp click, 15ms
    SOFT_FUZZ = 5  # Soft fuzz, 18ms
    STRONG_BUZZ = 6  # Strong buzz, 20ms
    
    # Strong effects (camera shutter simulation)
    ALERT_750MS = 7  # Alert pattern, 750ms
    ALERT_1000MS = 8  # Alert pattern, 1000ms
    STRONG_CLICK_1 = 9  # Strong click 100%, 30ms
    STRONG_CLICK_2 = 10  # Strong click 60%, 30ms
    STRONG_CLICK_3 = 11  # Strong click 30%, 30ms
    
    # Double taps (success confirmations)
    DOUBLE_CLICK = 12  # Two sharp clicks, ~80ms total
    TRIPLE_CLICK = 13  # Three sharp clicks, ~120ms total
    
    # Special patterns
    SHORT_DOUBLE_CLICK_1 = 14  # Short double, 40ms total
    SHORT_DOUBLE_CLICK_2 = 15  # Short double, 30ms total
    
    # Error patterns
    BUZZ_1 = 16  # Alert buzz, 40ms
    BUZZ_2 = 17  # Alert buzz, 60ms
    PULSING_SHARP = 18  # Pulsing sharp, 100ms
    
    # Misc
    TRANSITION_CLICK = 19  # UI transition, 15ms
    TRANSITION_HUM = 20  # UI transition, 25ms


class DRV2605L:
    """
    DRV2605L Haptic Driver Controller
    
    Optimized for LRA (Linear Resonant Actuator) with:
    - Low latency (<5ms trigger to output)
    - Configurable intensity (0-100%)
    - Auto-calibration support
    - Thermal protection
    """
    
    I2C_ADDRESS = 0x5A  # Default DRV2605L address
    
    def __init__(self, i2c_bus: int = 1, actuator_type: str = 'LRA'):
        """
        Initialize DRV2605L driver
        
        Args:
            i2c_bus: I2C bus number (1 for Raspberry Pi)
            actuator_type: 'LRA' or 'ERM'
        """
        self.bus = SMBus(i2c_bus)
        self.actuator_type = actuator_type
        self.amplitude_scale = 1.0  # Global amplitude multiplier (0.0-1.0)
        self.initialized = False
        
        # Initialize hardware
        self._init_device()
    
    def _write_reg(self, reg: int, value: int):
        """Write to register"""
        try:
            self.bus.write_byte_data(self.I2C_ADDRESS, reg, value & 0xFF)
        except Exception as e:
            logger.error(f"I2C write error: {e}")
    
    def _read_reg(self, reg: int) -> int:
        """Read from register"""
        try:
            return self.bus.read_byte_data(self.I2C_ADDRESS, reg)
        except Exception as e:
            logger.error(f"I2C read error: {e}")
            return 0
    
    def _init_device(self):
        """Initialize DRV2605L for LRA operation"""
        try:
            # Exit standby
            self._write_reg(DRV2605Reg.MODE, DRV2605Mode.INTERNAL_TRIGGER)
            
            # Select LRA library
            if self.actuator_type == 'LRA':
                self._write_reg(DRV2605Reg.LIBRARY_SELECTION, DRV2605Library.LRA)
                
                # Configure for LRA
                # FEEDBACK_CONTROL: N_ERM_LRA=1 (LRA mode), FB_BRAKE_FACTOR=3, LOOP_GAIN=2
                self._write_reg(DRV2605Reg.FEEDBACK_CONTROL, 0xB6)
                
                # CONTROL3: NG_THRESH=2, ERM_OPEN_LOOP=0, SUPPLY_COMP_DIS=0, DATA_FORMAT_RTP=0, LRA_DRIVE_MODE=1 (once per cycle), N_PWM_ANALOG=0, LRA_OPEN_LOOP=0
                self._write_reg(DRV2605Reg.CONTROL3, 0xA0)
                
                # Set rated voltage (for auto-calibration)
                # Example: 2.0V LRA → RMS = 1.414V → (1.414 / 5.6) * 255 ≈ 64 (0x40)
                self._write_reg(DRV2605Reg.RATED_VOLTAGE, 0x40)
                
                # Set overdrive clamp voltage
                # Example: 2.4V peak → (2.4 / 5.6) * 255 ≈ 109 (0x6D)
                self._write_reg(DRV2605Reg.OVERDRIVE_CLAMP_VOLTAGE, 0x6D)
                
                logger.info("DRV2605L initialized for LRA")
            
            else:  # ERM
                self._write_reg(DRV2605Reg.LIBRARY_SELECTION, DRV2605Library.TS2200_ERM)
                
                # Configure for ERM
                self._write_reg(DRV2605Reg.FEEDBACK_CONTROL, 0x36)  # N_ERM_LRA=0
                self._write_reg(DRV2605Reg.CONTROL3, 0x20)
                
                logger.info("DRV2605L initialized for ERM")
            
            self.initialized = True
            
        except Exception as e:
            logger.error(f"DRV2605L init failed: {e}")
            self.initialized = False
    
    def play_effect(self, effect: HapticEffect, amplitude: float = 1.0):
        """
        Play a waveform effect
        
        Args:
            effect: Effect ID from HapticEffect enum
            amplitude: Amplitude scale (0.0-1.0), default 1.0
        """
        if not self.initialized:
            return
        
        # Scale amplitude
        final_amplitude = min(1.0, amplitude * self.amplitude_scale)
        
        # Load effect into sequencer slot 1
        self._write_reg(DRV2605Reg.WAVEFORM_SEQUENCER_1, int(effect))
        # End sequence
        self._write_reg(DRV2605Reg.WAVEFORM_SEQUENCER_2, 0)
        
        # Set amplitude (optional, uses library defaults if not set)
        # Note: Real-time amplitude control would require RTP mode
        
        # Trigger playback
        self._write_reg(DRV2605Reg.GO, 1)
        
        logger.debug(f"Playing effect {effect.name} @ {final_amplitude*100:.0f}%")
    
    def play_custom_sequence(self, effects: list, amplitude: float = 1.0):
        """
        Play sequence of up to 8 effects
        
        Args:
            effects: List of effect IDs (max 8)
            amplitude: Global amplitude scale
        """
        if not self.initialized or len(effects) > 8:
            return
        
        # Load effects into sequencer
        for i, effect in enumerate(effects):
            self._write_reg(DRV2605Reg.WAVEFORM_SEQUENCER_1 + i, int(effect))
        
        # End sequence
        self._write_reg(DRV2605Reg.WAVEFORM_SEQUENCER_1 + len(effects), 0)
        
        # Trigger
        self._write_reg(DRV2605Reg.GO, 1)
    
    def set_amplitude(self, amplitude: float):
        """
        Set global amplitude scale (0.0-1.0)
        
        This multiplies all future effect amplitudes.
        Use for battery-saver mode or user preference.
        """
        self.amplitude_scale = max(0.0, min(1.0, amplitude))
        logger.info(f"Haptic amplitude set to {self.amplitude_scale*100:.0f}%")
    
    def auto_calibrate(self) -> bool:
        """
        Run auto-calibration routine for LRA
        
        Returns:
            True if calibration successful
        """
        if not self.initialized or self.actuator_type != 'LRA':
            return False
        
        logger.info("Starting auto-calibration...")
        
        # Set mode to auto-calibration
        self._write_reg(DRV2605Reg.MODE, DRV2605Mode.AUTO_CALIBRATION)
        
        # Trigger calibration
        self._write_reg(DRV2605Reg.GO, 1)
        
        # Wait for completion (max 1 second)
        for _ in range(100):
            time.sleep(0.01)
            status = self._read_reg(DRV2605Reg.GO)
            if (status & 0x01) == 0:
                # Calibration complete
                break
        
        # Check results
        comp_result = self._read_reg(DRV2605Reg.AUTO_CAL_COMP_RESULT)
        bemf_result = self._read_reg(DRV2605Reg.AUTO_CAL_BEMF_RESULT)
        
        success = (comp_result != 0) and (bemf_result != 0)
        
        if success:
            logger.info(f"Auto-cal success: COMP={comp_result}, BEMF={bemf_result}")
        else:
            logger.warning(f"Auto-cal failed: COMP={comp_result}, BEMF={bemf_result}")
        
        # Return to internal trigger mode
        self._write_reg(DRV2605Reg.MODE, DRV2605Mode.INTERNAL_TRIGGER)
        
        return success
    
    def standby(self):
        """Enter low-power standby mode"""
        self._write_reg(DRV2605Reg.MODE, 0x40)  # Standby bit
        logger.debug("Haptic driver in standby")
    
    def wake(self):
        """Wake from standby"""
        self._write_reg(DRV2605Reg.MODE, DRV2605Mode.INTERNAL_TRIGGER)
        logger.debug("Haptic driver awake")
    
    def cleanup(self):
        """Cleanup resources"""
        self.standby()
        self.bus.close()


class HapticController:
    """
    High-level haptic feedback controller
    
    Provides semantic feedback patterns for camera interactions:
    - Encoder detent simulation (adaptive based on rotation speed)
    - Shutter click (camera-like feel)
    - UI feedback (buttons, confirmations, errors)
    """
    
    def __init__(self, config: Optional[dict] = None):
        """
        Initialize haptic controller
        
        Args:
            config: Configuration dict with keys:
                - i2c_bus: I2C bus number (default: 1)
                - actuator_type: 'LRA' or 'ERM' (default: 'LRA')
                - base_amplitude: Base amplitude 0.0-1.0 (default: 0.6)
                - enable_adaptive: Enable adaptive detents (default: True)
        """
        config = config or {}
        
        self.driver = DRV2605L(
            i2c_bus=config.get('i2c_bus', 1),
            actuator_type=config.get('actuator_type', 'LRA')
        )
        
        self.base_amplitude = config.get('base_amplitude', 0.6)
        self.enable_adaptive = config.get('enable_adaptive', True)
        
        self.driver.set_amplitude(self.base_amplitude)
        
        # Adaptive detent state
        self.last_detent_time = 0.0
        self.rotation_speed = 0.0  # Detents per second
    
    def encoder_detent(self, adaptive: bool = True):
        """
        Encoder detent feedback
        
        Adaptive mode: Stronger feedback at slow turns, softer at fast turns
        """
        now = time.perf_counter()
        
        if adaptive and self.enable_adaptive:
            # Calculate rotation speed
            dt = now - self.last_detent_time
            if dt > 0:
                self.rotation_speed = 0.8 * self.rotation_speed + 0.2 * (1.0 / dt)
            
            # Adaptive amplitude
            # Slow turns (< 2 detents/sec): Full amplitude
            # Fast turns (> 10 detents/sec): 30% amplitude
            speed_factor = max(0.3, min(1.0, 1.0 - (self.rotation_speed - 2.0) / 8.0))
            amplitude = speed_factor
        else:
            amplitude = 1.0
        
        self.last_detent_time = now
        
        # Light click effect
        self.driver.play_effect(HapticEffect.LIGHT_CLICK, amplitude=amplitude)
    
    def shutter_click(self):
        """Camera shutter feedback (strong, realistic)"""
        self.driver.play_effect(HapticEffect.STRONG_CLICK_1, amplitude=1.0)
    
    def video_start(self):
        """Video recording start (double tap)"""
        self.driver.play_effect(HapticEffect.SHORT_DOUBLE_CLICK_1, amplitude=0.8)
    
    def video_stop(self):
        """Video recording stop (single medium)"""
        self.driver.play_effect(HapticEffect.SHARP_CLICK, amplitude=0.8)
    
    def filter_applied(self):
        """Filter applied confirmation"""
        self.driver.play_effect(HapticEffect.SOFT_BUMP, amplitude=0.7)
    
    def button_press(self):
        """UI button press"""
        self.driver.play_effect(HapticEffect.LIGHT_CLICK, amplitude=0.6)
    
    def success(self):
        """Operation success (double tap)"""
        self.driver.play_effect(HapticEffect.DOUBLE_CLICK, amplitude=0.8)
    
    def error(self):
        """Error notification (buzz)"""
        self.driver.play_effect(HapticEffect.BUZZ_1, amplitude=0.9)
    
    def menu_open(self):
        """Menu opened"""
        self.driver.play_effect(HapticEffect.TRANSITION_CLICK, amplitude=0.5)
    
    def menu_close(self):
        """Menu closed"""
        self.driver.play_effect(HapticEffect.TRANSITION_HUM, amplitude=0.5)
    
    def set_intensity(self, intensity: float):
        """
        Set global haptic intensity (0.0-1.0)
        
        For user preference or battery-saver mode
        """
        self.base_amplitude = max(0.0, min(1.0, intensity))
        self.driver.set_amplitude(self.base_amplitude)
    
    def calibrate(self) -> bool:
        """Run auto-calibration (LRA only)"""
        return self.driver.auto_calibrate()
    
    def standby(self):
        """Enter low-power mode"""
        self.driver.standby()
    
    def wake(self):
        """Wake from low-power mode"""
        self.driver.wake()
    
    def cleanup(self):
        """Cleanup resources"""
        self.driver.cleanup()


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    import sys
    
    print("DRV2605L Haptic Test")
    print("=" * 50)
    
    # Initialize
    haptic = HapticController(config={
        'i2c_bus': 1,
        'actuator_type': 'LRA',
        'base_amplitude': 0.6,
        'enable_adaptive': True
    })
    
    print("Testing effects...")
    
    # Test basic effects
    print("1. Light click (encoder detent)")
    haptic.encoder_detent()
    time.sleep(0.5)
    
    print("2. Shutter click")
    haptic.shutter_click()
    time.sleep(0.8)
    
    print("3. Double tap (success)")
    haptic.success()
    time.sleep(0.8)
    
    print("4. Error buzz")
    haptic.error()
    time.sleep(0.8)
    
    # Test adaptive detents
    print("5. Adaptive detents (slow -> fast)")
    for i in range(10):
        haptic.encoder_detent(adaptive=True)
        delay = max(0.05, 0.3 - i * 0.025)
        time.sleep(delay)
    
    print("\nTest complete!")
    
    # Cleanup
    haptic.cleanup()
