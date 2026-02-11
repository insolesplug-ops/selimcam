#!/bin/bash
#
# SelimCam Setup Script
# ======================
# 
# Automated installation for Raspberry Pi 3 Model B+
# 
# What this script does:
# 1. Install system dependencies
# 2. Install Python packages
# 3. Configure I2C, GPIO, Camera
# 4. Create directories and permissions
# 5. Install systemd service
# 6. Setup log rotation
# 
# Usage:
#   sudo ./setup.sh
# 
# Author: SelimCam Team
# License: MIT
#

set -e  # Exit on error

# Colors for output
RED='\033[0,31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (use sudo)"
    exit 1
fi

log_info "Starting SelimCam setup..."

# ============================================================================
# 1. SYSTEM UPDATE
# ============================================================================

log_info "Updating system packages..."
apt-get update
apt-get upgrade -y

# ============================================================================
# 2. INSTALL SYSTEM DEPENDENCIES
# ============================================================================

log_info "Installing system dependencies..."

apt-get install -y \
    python3-pip \
    python3-dev \
    python3-numpy \
    python3-pil \
    libcamera-apps \
    libcamera-dev \
    i2c-tools \
    python3-smbus \
    python3-rpi.gpio \
    git \
    cmake \
    build-essential \
    libjpeg-dev \
    libfreetype6-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libportmidi-dev \
    libswscale-dev \
    libavformat-dev \
    libavcodec-dev \
    zlib1g-dev \
    libzmq3-dev

# ============================================================================
# 3. ENABLE HARDWARE INTERFACES
# ============================================================================

log_info "Enabling hardware interfaces..."

# Enable I2C
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
    log_info "Enabling I2C..."
    echo "dtparam=i2c_arm=on" >> /boot/config.txt
fi

# Enable Camera
if ! grep -q "^dtoverlay=vc4-fkms-v3d" /boot/config.txt; then
    log_info "Enabling Camera..."
    echo "dtoverlay=vc4-fkms-v3d" >> /boot/config.txt
    echo "camera_auto_detect=1" >> /boot/config.txt
fi

# Set I2C speed (400kHz for DRV2605L)
if ! grep -q "^dtparam=i2c_arm_baudrate" /boot/config.txt; then
    log_info "Setting I2C speed to 400kHz..."
    echo "dtparam=i2c_arm_baudrate=400000" >> /boot/config.txt
fi

# Add user to i2c group
USER_NAME=$(logname)
usermod -a -G i2c,gpio,video $USER_NAME

# ============================================================================
# 4. INSTALL PYTHON PACKAGES
# ============================================================================

log_info "Installing Python packages..."

# Upgrade pip
python3 -m pip install --upgrade pip

# Install packages
python3 -m pip install --break-system-packages \
    picamera2 \
    pygame \
    numpy \
    pillow \
    pyzmq \
    smbus2 \
    RPi.GPIO \
    adafruit-circuitpython-drv2605 \
    pytest \
    pytest-benchmark

# ============================================================================
# 5. CREATE DIRECTORIES
# ============================================================================

log_info "Creating directories..."

# Installation directory
INSTALL_DIR="/opt/selimcam"
mkdir -p $INSTALL_DIR

# Data directories
mkdir -p /var/lib/selimcam/photos
mkdir -p /var/lib/selimcam/videos
mkdir -p /var/lib/selimcam/config
mkdir -p /var/lib/selimcam/logs

# Set permissions
chown -R $USER_NAME:$USER_NAME /var/lib/selimcam
chmod -R 755 /var/lib/selimcam

# ============================================================================
# 6. COPY FILES
# ============================================================================

log_info "Installing SelimCam files..."

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Copy application files
cp -r $SCRIPT_DIR/.. $INSTALL_DIR/
chown -R $USER_NAME:$USER_NAME $INSTALL_DIR

# Make scripts executable
chmod +x $INSTALL_DIR/scripts/*.sh
chmod +x $INSTALL_DIR/main.py

# ============================================================================
# 7. INSTALL SYSTEMD SERVICE
# ============================================================================

log_info "Installing systemd service..."

cat > /etc/systemd/system/selimcam.service << EOF
[Unit]
Description=SelimCam Camera Application
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$INSTALL_DIR
Environment="DISPLAY=:0"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/usr/bin/python3 $INSTALL_DIR/main_pi_prod.py
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/lib/selimcam/logs/selimcam.log
StandardError=append:/var/lib/selimcam/logs/selimcam_error.log

# Resource limits
MemoryLimit=420M
CPUQuota=200%

# Watchdog
WatchdogSec=30

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# Enable service (but don't start yet)
systemctl enable selimcam.service

log_info "Systemd service installed and enabled"

# ============================================================================
# 8. SETUP LOG ROTATION
# ============================================================================

log_info "Configuring log rotation..."

cat > /etc/logrotate.d/selimcam << EOF
/var/lib/selimcam/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 $USER_NAME $USER_NAME
    sharedscripts
    postrotate
        systemctl reload selimcam.service > /dev/null 2>&1 || true
    endscript
}
EOF

# ============================================================================
# 9. CONFIGURE DISPLAY (DSI LCD)
# ============================================================================

log_info "Configuring DSI display..."

# Disable HDMI output (save power)
if ! grep -q "^hdmi_blanking=2" /boot/config.txt; then
    echo "hdmi_blanking=2" >> /boot/config.txt
fi

# Disable screen blanking
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

# Create X11 config for touchscreen
mkdir -p /etc/X11/xorg.conf.d/
cat > /etc/X11/xorg.conf.d/99-calibration.conf << EOF
Section "InputClass"
    Identifier "calibration"
    MatchProduct "wch.cn USB2IIC_CTP_CONTROL"
    Option "Calibration" "0 800 0 480"
    Option "SwapAxes" "0"
EOF

# ============================================================================
# 10. PERFORMANCE TUNING
# ============================================================================

log_info "Applying performance optimizations..."

# CPU governor to performance mode
echo 'GOVERNOR="performance"' > /etc/default/cpufrequtils

# Disable swap (SD card wear)
dphys-swapfile swapoff || true
dphys-swapfile uninstall || true
systemctl disable dphys-swapfile || true

# GPU memory split (256MB for camera)
if ! grep -q "^gpu_mem=" /boot/config.txt; then
    echo "gpu_mem=256" >> /boot/config.txt
fi

# ============================================================================
# 11. CREATE CONFIGURATION FILE
# ============================================================================

log_info "Creating default configuration..."

cat > /var/lib/selimcam/config/config.json << EOF
{
    "camera": {
        "preview_width": 640,
        "preview_height": 480,
        "preview_fps": 30,
        "capture_width": 3280,
        "capture_height": 2464,
        "capture_quality": 95,
        "hflip": false,
        "vflip": false
    },
    "hardware": {
        "encoder_pin_a": 5,
        "encoder_pin_b": 6,
        "encoder_button": 13,
        "shutter_button": 26,
        "haptic_i2c_bus": 1,
        "haptic_amplitude": 0.6
    },
    "ui": {
        "screen_width": 800,
        "screen_height": 480,
        "fullscreen": true,
        "fps": 30
    },
    "performance": {
        "enable_multiprocess": false,
        "worker_threads": 2,
        "preview_buffer_count": 3
    }
}
EOF

chown $USER_NAME:$USER_NAME /var/lib/selimcam/config/config.json

# ============================================================================
# 12. HARDWARE TEST UTILITIES
# ============================================================================

log_info "Installing hardware test utilities..."

cat > $INSTALL_DIR/scripts/test_hardware.sh << 'EOF'
#!/bin/bash
# Hardware test script

echo "SelimCam Hardware Test"
echo "======================"
echo

echo "[I2C Devices]"
i2cdetect -y 1

echo
echo "[Camera]"
libcamera-hello --list-cameras

echo
echo "[GPIO]"
gpio readall

echo
echo "Test complete!"
EOF

chmod +x $INSTALL_DIR/scripts/test_hardware.sh

# ============================================================================
# 13. CREATE LAUNCHER SCRIPT
# ============================================================================

log_info "Creating launcher script..."

cat > /usr/local/bin/selimcam << EOF
#!/bin/bash
# SelimCam launcher

case "\$1" in
    start)
        sudo systemctl start selimcam.service
        ;;
    stop)
        sudo systemctl stop selimcam.service
        ;;
    restart)
        sudo systemctl restart selimcam.service
        ;;
    status)
        sudo systemctl status selimcam.service
        ;;
    logs)
        sudo journalctl -u selimcam.service -f
        ;;
    test)
        cd $INSTALL_DIR && python3 -m pytest tests/ -v
        ;;
    benchmark)
        cd $INSTALL_DIR && python3 tests/test_integration.py
        ;;
    *)
        echo "Usage: selimcam {start|stop|restart|status|logs|test|benchmark}"
        exit 1
        ;;
esac
EOF

chmod +x /usr/local/bin/selimcam

# ============================================================================
# SETUP COMPLETE
# ============================================================================

log_info ""
log_info "============================================"
log_info "SelimCam setup complete!"
log_info "============================================"
log_info ""
log_info "Next steps:"
log_info "  1. Reboot the system: sudo reboot"
log_info "  2. After reboot, test hardware: sudo $INSTALL_DIR/scripts/test_hardware.sh"
log_info "  3. Start SelimCam: selimcam start"
log_info "  4. View logs: selimcam logs"
log_info "  5. Run tests: selimcam test"
log_info ""
log_info "Configuration: /var/lib/selimcam/config/config.json"
log_info "Logs: /var/lib/selimcam/logs/"
log_info "Photos: /var/lib/selimcam/photos/"
log_info ""
log_warn "IMPORTANT: System reboot required for hardware changes to take effect!"
log_info ""

# Ask for reboot
read -p "Reboot now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "Rebooting..."
    reboot
fi


log_info "Running optional diagnostics..."
python3 /opt/selimcam/diagnostics.py || log_warn "Diagnostics skipped/failed"
