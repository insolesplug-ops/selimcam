# Developer Notes - SelimCam
# ============================

This document provides technical guidance for:
- Porting to different Raspberry Pi models
- Swapping hardware components
- Extending functionality
- Performance optimization
- Debugging tips

## 🔄 Porting to Different Pi Models

### Raspberry Pi 4 (Recommended Upgrade)

**Benefits:**
- 4GB/8GB RAM (vs 1GB on Pi 3B+)
- Faster CPU (1.5GHz quad-core Cortex-A72 vs 1.4GHz A53)
- USB 3.0 for faster storage
- Gigabit Ethernet
- Dual 4K display support

**Changes Required:**

1. **Power Supply**
   - Pi 4 requires 5V/3A (vs 2.5A for Pi 3)
   - Update UPS HAT or use official Pi 4 power supply
   - May need higher capacity battery (4000mAh+)

2. **GPIO Pinout**
   - Same 40-pin header (fully compatible)
   - No wiring changes needed

3. **Camera Interface**
   - Use libcamera (same as Pi 3)
   - Supports dual cameras (use both front + rear!)
   ```python
   camera_config = {
       'camera_index': 0,  # 0 = first camera, 1 = second
   }
   ```

4. **Performance Tuning**
   - Increase preview resolution to 1280x720 (from 640x480)
   - Enable 60 FPS preview
   ```python
   # config/settings.py
   PREVIEW_WIDTH = 1280
   PREVIEW_HEIGHT = 720
   PREVIEW_FPS = 60
   ```

5. **Memory Management**
   - Allocate more GPU memory (512MB vs 256MB)
   ```bash
   # /boot/config.txt
   gpu_mem=512
   ```

### Raspberry Pi 5

**Benefits:**
- Much faster (2.4GHz Cortex-A76)
- PCIe support (NVMe SSD possible!)
- Better camera ISP
- AI accelerator compatible

**Changes Required:**

1. **Power**
   - Requires 5V/5A for full performance
   - Recommend separate power board

2. **Camera**
   - Use new libcamera API
   - 4K video possible at 30fps
   ```python
   video_config = {
       'video_width': 3840,
       'video_height': 2160,
       'video_fps': 30
   }
   ```

3. **GPIO**
   - Same pinout (compatible)
   - Faster GPIO (helpful for encoder)

4. **Performance**
   - Can run ML scene detection in real-time
   - Enable TensorFlow Lite:
   ```python
   # In camera_service.py
   import tflite_runtime.interpreter as tflite
   interpreter = tflite.Interpreter(model_path="scene_detector.tflite")
   ```

### Raspberry Pi Zero 2 W (Compact Build)

**Trade-offs:**
- Much smaller (65mm x 30mm)
- Lower power (good for battery)
- But: Only 512MB RAM, slower CPU

**Changes:**

1. **Performance Limits**
   - Reduce preview to 480x360 @ 24fps
   - Disable live filters (too slow)
   - Use simpler UI (no animations)

2. **Memory**
   ```python
   # Reduce buffer count
   buffer_count = 2  # Instead of 3
   
   # Use 16-bit images for preview
   preview_format = 'RGB565'  # Instead of RGB888
   ```

3. **GPIO**
   - Only 40 pins (same pinout, but less space)
   - Consider I2C GPIO expander for more pins

---

## 🔧 Swapping Hardware Components

### Alternative Haptic Actuators

#### Using ERM (Eccentric Rotating Mass) Instead of LRA

**Pros:** Cheaper ($1 vs $3)
**Cons:** Slower response, less precise, coarser feel

**Changes:**
```python
# hardware/haptic_driver.py

# Change actuator type
haptic = HapticController(config={
    'actuator_type': 'ERM'  # Instead of 'LRA'
})

# ERM takes longer to spin up/down
# Increase effect duration for same feel:
LIGHT_CLICK_DURATION = 25  # ms (vs 10ms for LRA)
```

**DRV2605L Settings:**
```python
# In DRV2605L._init_device()
self._write_reg(DRV2605Reg.LIBRARY_SELECTION, DRV2605Library.TS2200_ERM)
self._write_reg(DRV2605Reg.FEEDBACK_CONTROL, 0x36)  # N_ERM_LRA=0
```

#### Using Direct GPIO (Not Recommended)

For simple vibration motor without DRV2605L:

```python
import RPi.GPIO as GPIO

MOTOR_PIN = 27

GPIO.setmode(GPIO.BCM)
GPIO.setup(MOTOR_PIN, GPIO.OUT)
pwm = GPIO.PWM(MOTOR_PIN, 100)  # 100Hz

def vibrate(duration_ms, strength=50):
    """
    Vibrate motor
    duration_ms: vibration time in ms
    strength: PWM duty cycle (0-100%)
    """
    pwm.start(strength)
    time.sleep(duration_ms / 1000.0)
    pwm.stop()

# Use:
vibrate(20, strength=60)  # 20ms at 60% power
```

**CRITICAL:** Add flyback diode (1N4148) and current-limiting resistor!

### Alternative Rotary Encoders

#### Using Bourns PEC11 Series

Very similar to ALPS EC11:
- Same mechanical interface
- Same electrical specs
- No code changes needed

#### Using Cheaper Encoder (e.g., KY-040)

**Lower quality but functional:**

```python
# May need to adjust debounce time
encoder = RotaryEncoder(
    debounce_ms=5.0,  # Increase from 2.0ms
)

# May need software filtering for noise
class FilteredEncoder:
    def __init__(self, encoder):
        self.encoder = encoder
        self.history = []
    
    def poll(self):
        self.encoder.poll()
        
        # Filter spurious events
        self.history.append(self.encoder.position)
        self.history = self.history[-3:]
        
        # Only accept if 2 out of 3 agree
        if len(set(self.history)) == 1:
            return self.history[0]
```

### Alternative Displays

#### Using HDMI Display Instead of DSI

```bash
# No hardware changes needed
# Just connect HDMI cable

# May need to adjust resolution
# In config/settings.py:
SCREEN_WIDTH = 1920  # Your display resolution
SCREEN_HEIGHT = 1080
```

#### Using e-Ink Display (For Low Power)

**Good for:** Always-on display, battery life
**Bad for:** Slow refresh (can't do video preview)

```python
# Use Waveshare e-Paper HAT
from waveshare_epd import epd4in2

epd = epd4in2.EPD()
epd.init()

# Update only when needed (not 30fps!)
def update_display(image):
    epd.display(epd.getbuffer(image))
    # Takes ~2 seconds to refresh
```

---

## 🚀 Extending Functionality

### Adding New Filters

1. Create filter class:

```python
# filters/custom_filters.py

from filters.filters import BaseFilter, FilterType
import numpy as np

class SepiaToneFilter(BaseFilter):
    def __init__(self):
        super().__init__("Sepia", FilterType.COLOR)
    
    def apply(self, image: np.ndarray, strength: float = 1.0) -> np.ndarray:
        # Sepia matrix
        sepia_matrix = np.array([
            [0.393, 0.769, 0.189],
            [0.349, 0.686, 0.168],
            [0.272, 0.534, 0.131]
        ])
        
        # Apply matrix
        sepia = np.dot(image[..., :3], sepia_matrix.T)
        sepia = np.clip(sepia, 0, 255)
        
        # Blend with original
        result = image.copy()
        result[..., :3] = (1 - strength) * image + strength * sepia
        
        return result.astype(np.uint8)
```

2. Register filter:

```python
# In FilterManager._init_filters()
self.filters['sepia'] = SepiaToneFilter()
self.presets['vintage_warm'] = ['sepia', 'brightness']
```

### Adding Remote API

Enable remote control and preview:

```python
# Create api/remote_server.py

from aiohttp import web
import asyncio
import base64
import io
from PIL import Image

class RemoteAPI:
    def __init__(self, camera_service, port=8080):
        self.camera = camera_service
        self.app = web.Application()
        self.app.router.add_get('/preview', self.get_preview)
        self.app.router.add_post('/capture', self.capture_photo)
        self.app.router.add_post('/zoom', self.set_zoom)
        self.port = port
    
    async def get_preview(self, request):
        """Get current preview frame as JPEG"""
        frame = self.camera.get_preview_frame()
        
        if frame is None:
            return web.Response(status=503)
        
        # Convert to JPEG
        img = Image.fromarray(frame)
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        
        return web.Response(
            body=buffer.getvalue(),
            content_type='image/jpeg'
        )
    
    async def capture_photo(self, request):
        """Trigger photo capture"""
        # TODO: Implement async capture
        return web.json_response({'status': 'ok'})
    
    def start(self):
        web.run_app(self.app, port=self.port)
```

Usage:
```python
# In main.py
from api.remote_server import RemoteAPI

api = RemoteAPI(camera_service, port=8080)
threading.Thread(target=api.start, daemon=True).start()
```

Access:
```bash
# Get preview
curl http://pi.local:8080/preview > preview.jpg

# Capture photo
curl -X POST http://pi.local:8080/capture
```

### Adding ML Scene Detection

Use TensorFlow Lite for real-time classification:

```python
# Install TFLite
pip install tflite-runtime

# Create ml/scene_detector.py
import tflite_runtime.interpreter as tflite
import numpy as np

class MLSceneDetector:
    def __init__(self, model_path='models/scene_detector.tflite'):
        self.interpreter = tflite.Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        
        self.labels = ['portrait', 'landscape', 'night', 'action', 'macro']
    
    def predict(self, frame: np.ndarray) -> str:
        """
        Predict scene type
        
        Args:
            frame: RGB image (any size, will be resized)
        
        Returns:
            Scene label (e.g., 'portrait')
        """
        # Resize to model input size (e.g., 224x224)
        input_shape = self.input_details[0]['shape']
        frame_resized = cv2.resize(frame, (input_shape[1], input_shape[2]))
        
        # Normalize to [0, 1]
        frame_norm = frame_resized.astype(np.float32) / 255.0
        
        # Add batch dimension
        input_data = np.expand_dims(frame_norm, axis=0)
        
        # Inference
        self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
        self.interpreter.invoke()
        
        # Get prediction
        output_data = self.interpreter.get_tensor(self.output_details[0]['index'])
        predicted_idx = np.argmax(output_data[0])
        
        return self.labels[predicted_idx]
```

---

## ⚡ Performance Optimization

### Profiling

```python
# Add to any module
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# ... code to profile ...

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumtime')
stats.print_stats(20)  # Top 20 slowest functions
```

### Memory Profiling

```python
from memory_profiler import profile

@profile
def my_function():
    # Function to profile
    pass
```

### CPU Affinity

Pin processes to specific cores:

```python
import os

def set_cpu_affinity(core_ids):
    """Pin process to specific CPU cores"""
    os.sched_setaffinity(0, core_ids)

# In camera process
set_cpu_affinity([0, 1])  # Use cores 0 and 1

# In UI process  
set_cpu_affinity([2, 3])  # Use cores 2 and 3
```

### NEON Optimization (ARM)

For intensive image processing, use ARM NEON intrinsics:

```python
# Install Ne10 library
sudo apt install libne10-dev

# Use NumPy with BLAS/LAPACK (automatically uses NEON)
import numpy as np

# Or write Cython extension with NEON
# filters/neon_filters.pyx
```

---

## 🐞 Debugging Tips

### Enable Verbose Logging

```python
# In main.py
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/var/lib/selimcam/logs/debug.log'),
        logging.StreamHandler()
    ]
)
```

### Live Performance Monitoring

```python
# Add to main loop
if DEBUG:
    print(f"FPS: {fps:.1f}, Frame: {frame_time_ms:.1f}ms, "
          f"CPU: {psutil.cpu_percent():.1f}%, "
          f"RAM: {psutil.virtual_memory().percent:.1f}%")
```

### I2C Debugging

```bash
# Watch I2C traffic
sudo i2cdump -y 1 0x5A  # Dump DRV2605L registers

# Monitor continuously
watch -n 0.5 'i2cget -y 1 0x5A 0x00'  # Status register
```

### GPIO State Monitoring

```python
# Log all GPIO changes
import RPi.GPIO as GPIO

GPIO.add_event_detect(5, GPIO.BOTH, callback=lambda ch: print(f"GPIO {ch}: {GPIO.input(ch)}"))
```

---

## 📝 Code Style Guidelines

Follow PEP 8 with these additions:

```python
# Type hints everywhere
def process_image(image: np.ndarray, filter_name: str) -> np.ndarray:
    pass

# Docstrings for all public functions
def capture_photo(filepath: Path, quality: int = 95) -> bool:
    """
    Capture full-resolution photo
    
    Args:
        filepath: Output file path
        quality: JPEG quality (1-100)
    
    Returns:
        True if successful
    
    Raises:
        CameraError: If capture fails
    """
    pass

# Use dataclasses for configuration
from dataclasses import dataclass

@dataclass
class CameraConfig:
    preview_width: int = 640
    preview_height: int = 480
    capture_quality: int = 95
```

---

## 🔐 Security Considerations

### Remote API Authentication

```python
# Add JWT authentication
from aiohttp_jwt import JWTMiddleware

middleware = JWTMiddleware(
    secret_or_pub_key='your-secret-key',
    request_property='user',
    credentials_required=True
)

app = web.Application(middlewares=[middleware])
```

### Secure File Permissions

```bash
# Set restrictive permissions
chmod 600 /var/lib/selimcam/config/config.json
chown pi:pi /var/lib/selimcam/photos
chmod 755 /var/lib/selimcam/photos
```

---

## 📚 Additional Resources

- [Raspberry Pi Documentation](https://www.raspberrypi.org/documentation/)
- [Picamera2 Manual](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf)
- [DRV2605L Application Note](https://www.ti.com/lit/an/sloa194/sloa194.pdf)
- [Python Performance Tips](https://wiki.python.org/moin/PythonSpeed/PerformanceTips)

---

*Last updated: 2025-02-11*
*Version: 6.0*
