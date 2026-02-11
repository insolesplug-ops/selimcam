# SelimCam Hardware Documentation
# =================================

## 📋 Bill of Materials (BOM)

### Core Components

| Item | Part Number | Description | Quantity | Source | Price (approx) |
|------|-------------|-------------|----------|--------|----------------|
| **Compute** |
| Raspberry Pi 3 Model B+ | RPi 3B+ | 1.4GHz quad-core, 1GB RAM | 1 | Raspberry Pi Foundation | $35 |
| MicroSD Card | SanDisk Extreme PRO 64GB A2 | Application Performance Class 2 | 1 | SanDisk | $15 |
| **Display** |
| DSI LCD | Waveshare 4.3" DSI LCD | 800x480, capacitive touch | 1 | Waveshare | $45 |
| Screen Protector | Nintendo Switch Screen Protector | Matte/anti-glare (cut to size) | 1 | Generic | $8 |
| **Camera** |
| Camera Module | OV5647 5MP | Vintage-look sensor | 1 | Generic | $15 |
| Alt. Camera | IMX219 8MP | Higher resolution option | 1 | Sony/Arducam | $25 |
| **Power System** |
| UPS HAT | Waveshare UPS HAT (C) | 5V/2A power + charging | 1 | Waveshare | $25 |
| Power Switch | Adafruit Push-button Power Switch | Smart power control | 1 | Adafruit #1400 | $5 |
| LiPo Battery | 3.7V 2500-4000mAh | Flat form factor | 1 | Generic | $12-20 |
| USB-C Breakout | USB-C Breakout Board | For charging port | 1 | Adafruit #4090 | $3 |
| **Input Controls** |
| Rotary Encoder | ALPS EC11 | 15mm D-shaft, 24 detents | 1 | ALPS | $3 |
| Encoder Knob | Aluminum Knob | For 6mm D-shaft | 1 | Generic | $5 |
| Shutter Button | Tactile Switch | 12-17mm, momentary | 1 | Generic | $1 |
| **Haptic Feedback** |
| Haptic Driver | DRV2605L Breakout | I2C haptic motor driver | 1 | Adafruit #2305 | $8 |
| LRA Actuator | Jinlong Z4TL1B0140091 | 10mm coin LRA, 2V, 150Hz | 1 | Jinlong | $3 |
| **Sensors** |
| Gyroscope | L3G4200D | 3-axis gyro (motion detection) | 1 | STMicro | $4 |
| Light Sensor | BH1750 | Digital ambient light sensor | 1 | ROHM | $2 |
| **Electronics** |
| Capacitor | 1000µF 10V | Low ESR, power decoupling | 1 | Generic | $0.50 |
| Transistor NPN | BC547 | For shutdown signal | 1 | Generic | $0.10 |
| Transistor NPN | BC337 | For motor/LED drive | 1 | Generic | $0.10 |
| Resistors | | See detailed list below | | Generic | $2 |
| Diodes | 1N4148 | Flyback diode for motor | 1 | Generic | $0.10 |
| LED | 5mm Warm White | High power, 18000mcd | 1 | Generic | $0.50 |
| **Miscellaneous** |
| Fuse | 500mA Resettable PTC | For haptic driver | 1 | Littelfuse | $0.50 |
| Wire | 26-28 AWG | Stranded, various colors | 1m | Generic | $3 |
| Heat Shrink | Assorted sizes | For insulation | 1 set | Generic | $3 |
| **TOTAL** | | | | | **~$220-240** |

### Detailed Resistor List

| Value | Power Rating | Quantity | Purpose |
|-------|--------------|----------|---------|
| 22Ω | 0.6W | 1 | LED current limiting |
| 1kΩ | 0.25W | 2 | Transistor base resistors |
| 2.2kΩ | 0.25W | 2 | I2C pull-ups |
| 10kΩ | 0.25W | 4 | Encoder/button pull-ups (optional) |

---

## 🔌 Wiring Diagram

### Power System Architecture

```
┌─────────────┐
│  LiPo       │
│  Battery    │
│  3.7V       │
└──────┬──────┘
       │ +
       │
       ├─────────────────────────────────┐
       │                                 │
┌──────▼──────────┐              ┌──────▼──────┐
│  Adafruit       │              │   Fuse      │
│  Power Switch   │              │   500mA     │
│  (Smart Cut)    │              └──────┬──────┘
└──────┬──────────┘                     │
       │ OUT                            │
       │                                │
┌──────▼───────────────────────────────▼─┐
│  Waveshare UPS HAT (C)                 │
│  - 5V Boost Converter                  │
│  - Charge Management                   │
│  - Battery Protection                  │
└──────┬─────────────────────────────────┘
       │ 5V/2A
       │
┌──────▼──────────┐
│  1000µF/10V     │  ← CRITICAL: Power decoupling
│  Capacitor      │
└──────┬──────────┘
       │
┌──────▼──────────┐
│  Raspberry Pi   │
│  PP2/PP3 Pads   │
│  (5V + GND)     │
└─────────────────┘
```

### GPIO Pin Assignments

```
Raspberry Pi GPIO Pinout (BCM numbering)

      3.3V  (1) (2)  5V
 SDA1/GPIO2  (3) (4)  5V
 SCL1/GPIO3  (5) (6)  GND
      GPIO4  (7) (8)  GPIO14
        GND  (9) (10) GPIO15
      GPIO17 (11)(12) GPIO18
      GPIO27 (13)(14) GND
      GPIO22 (15)(16) GPIO23
      3.3V  (17)(18) GPIO24
     GPIO10  (19)(20) GND
      GPIO9  (21)(22) GPIO25
     GPIO11  (23)(24) GPIO8
        GND  (25)(26) GPIO7
      GPIO0  (27)(28) GPIO1
      GPIO5  (29)(30) GND
      GPIO6  (31)(32) GPIO12
     GPIO13  (33)(34) GND
     GPIO19  (35)(36) GPIO16
     GPIO26  (37)(38) GPIO20
        GND  (39)(40) GPIO21

PIN ASSIGNMENTS:
================

Power:
  1  - 3.3V  → Sensors VCC
  2  - 5V    → Motor/LED power
  6  - GND   → Common ground

I2C (for DRV2605L, BH1750, L3G4200D):
  3  - GPIO2  (SDA1) → I2C SDA + 2.2kΩ pull-up to 3.3V
  5  - GPIO3  (SCL1) → I2C SCL + 2.2kΩ pull-up to 3.3V

Rotary Encoder:
  29 - GPIO5  → Encoder A
  31 - GPIO6  → Encoder B
  33 - GPIO13 → Encoder Button (wake + select)

Shutter Button:
  37 - GPIO26 → Shutter (half-press capable)

Haptic/LED Control:
  13 - GPIO27 → Flash LED control (via BC337)

Auto-Shutdown:
  35 - GPIO19 → Shutdown signal (via BC547 to power switch)
```

### Detailed Component Wiring

#### 1. DRV2605L Haptic Driver

```
DRV2605L Breakout (Adafruit #2305)
┌─────────────────┐
│ VIN  → 3.3V     │  Pin 1 (3.3V)
│ GND  → GND      │  Pin 6 (GND)
│ SDA  → GPIO2    │  Pin 3 (I2C SDA)
│ SCL  → GPIO3    │  Pin 5 (I2C SCL)
│ IN+  → LRA+     │  ─┐
│ IN-  → LRA-     │  ─┤  To LRA Actuator
└─────────────────┘   │  (Jinlong Z4TL1B0140091)
                      └─ 10mm coin LRA

IMPORTANT:
- Add 10µF + 0.1µF decoupling caps on VDD pin
- LRA polarity doesn't matter (AC drive)
- Keep wires short (<10cm) to reduce EMI
- Optional: 500mA PTC fuse on VIN for safety
```

#### 2. Rotary Encoder with Debouncing

```
ALPS EC11 Encoder
┌─────────────────┐
│      A  → GPIO5 │ ────┬─── Pin 29
│      C  → GND   │      │
│      B  → GPIO6 │ ──┬──┼─── Pin 31
│    SW1  → GPIO3 │   │  │
│    SW2  → GND   │   │  │
└─────────────────┘   │  │
                      │  │
HARDWARE DEBOUNCING (Recommended):
                      │  │
For each signal (A, B):
  GPIO Pin ─┬─── 100nF ─── GND
            │
            └─── 10kΩ ─── 3.3V

Alternative: Schmitt Trigger (74HC14)
  Encoder → 74HC14 → GPIO
  (Best for >20 detents/sec)

SOFTWARE DEBOUNCING:
  Handled in rotary_encoder.py
  - ISR-based edge detection
  - 2ms debounce time
  - Gray code state machine
```

#### 3. Power Control Circuit

```
AUTO-SHUTDOWN CIRCUIT:
======================

GPIO19 ────┬─── 1kΩ ─── BC547(Base)
           │
           └─── Optional pull-down

BC547(Collector) ─── Adafruit Switch "OFF" pin
BC547(Emitter)   ─── GND

How it works:
1. When GPIO19 goes HIGH, BC547 conducts
2. Pulls Adafruit Switch OFF pin LOW
3. Switch cuts power to UPS HAT
4. System shuts down cleanly

WAKE-UP CIRCUIT:
================

Encoder Button ─── Adafruit Switch "ON" pin ─── GPIO3
                                    │
                                    └─── 1N4148 ─── 3.3V
                                         (Diode, stripe to Pi)

How it works:
1. Press encoder button → pulls ON pin LOW
2. Adafruit Switch connects battery to UPS HAT
3. Pi boots
4. GPIO3 can also wake Pi from sleep (with dtoverlay)
```

#### 4. Flash LED Circuit

```
FLASH LED DRIVER:
=================

5V ─── 22Ω (0.6W) ─── LED Anode
                      │
                      └─── LED Cathode
                           │
                      BC337(Collector)
                           │
                      BC337(Emitter) ─── GND

GPIO27 ─── 1kΩ ─── BC337(Base)

Specifications:
- LED: 5mm Warm White, 18000mcd, Vf=3.2V @ 20mA
- Resistor: (5V - 3.2V) / 0.02A = 90Ω → use 100Ω for safety
  (22Ω shown is for higher current - adjust based on LED spec)
- BC337: NPN transistor, max 800mA collector current
- CRITICAL: Never drive LED directly from GPIO (max 16mA)!
```

#### 5. Sensors (I2C)

```
BH1750 Light Sensor
┌─────────────────┐
│ VCC → 3.3V      │  Pin 1
│ GND → GND       │  Pin 6
│ SDA → GPIO2     │  Pin 3
│ SCL → GPIO3     │  Pin 5
│ ADDR → GND      │  (Address 0x23)
└─────────────────┘

L3G4200D Gyroscope
┌─────────────────┐
│ VCC → 3.3V      │  Pin 1
│ GND → GND       │  Pin 6
│ SDA → GPIO2     │  Pin 3
│ SCL → GPIO3     │  Pin 5
└─────────────────┘

I2C Pull-ups (SHARED):
  GPIO2 (SDA) ─── 2.2kΩ ─── 3.3V
  GPIO3 (SCL) ─── 2.2kΩ ─── 3.3V

I2C Bus Addresses:
  0x23 - BH1750 (light sensor)
  0x5A - DRV2605L (haptic driver)
  0x69 - L3G4200D (gyro, default)
```

---

## ⚠️ Safety Notes & Best Practices

### CRITICAL SAFETY RULES

1. **Power Decoupling**
   - ALWAYS use 1000µF capacitor on Pi 5V rail
   - Add 10µF + 0.1µF caps on all IC VDD pins
   - Place capacitors as close as possible to power pins

2. **Current Limits**
   - GPIO max current: 16mA per pin, 50mA total
   - NEVER drive motors/LEDs directly from GPIO
   - Use transistors (BC337, BC547) for all loads >5mA

3. **LiPo Battery Safety**
   - Use protected batteries with built-in PCM
   - Never discharge below 3.0V
   - Charge at max 1C rate (e.g., 2.5A for 2500mAh)
   - Store at 3.7-3.8V for long-term storage
   - Keep away from metal objects (short circuit hazard!)

4. **I2C Bus**
   - Max speed: 400kHz (set in config.txt)
   - Always use pull-up resistors (2.2kΩ-4.7kΩ)
   - Keep bus wires <30cm to reduce noise
   - Avoid star topology, use daisy-chain

5. **ESD Protection**
   - Wear anti-static wrist strap when handling Pi
   - Work on ESD-safe mat
   - Store in anti-static bag

### Troubleshooting

#### I2C Device Not Detected

```bash
# Check I2C is enabled
ls /dev/i2c-*

# Scan I2C bus
i2cdetect -y 1

# Expected addresses:
#   0x23 - BH1750
#   0x5A - DRV2605L  
#   0x69 - L3G4200D

# If missing, check:
# 1. Power connections (3.3V, GND)
# 2. Pull-up resistors on SDA/SCL
# 3. Wiring (no shorts, correct pins)
```

#### Haptic Driver Not Working

```bash
# Test I2C communication
i2cget -y 1 0x5A 0x00

# Should return status register (non-zero)

# Common issues:
# 1. Missing pull-up resistors
# 2. Wrong I2C address (should be 0x5A)
# 3. LRA not connected
# 4. Insufficient power (use capacitors!)
```

#### Encoder Not Responding

```bash
# Check GPIO state
gpio readall

# Test encoder manually:
# 1. Turn encoder slowly
# 2. Run: python3 -c "from hardware.rotary_encoder import RotaryEncoder; ..."

# Common issues:
# 1. Software pull-ups not enabled
# 2. Bouncing (add hardware debouncing)
# 3. Wrong pins in config
```

---

## 🔧 Assembly Instructions

### Step 1: Prepare Raspberry Pi

1. Modify Pi (optional, for compact build):
   - Desolder USB ports
   - Desolder HDMI port
   - Desolder audio jack
   - Bend or trim GPIO header

2. Solder power wires to PP2/PP3 test pads
   - PP2 → 5V
   - PP3 → GND

### Step 2: Power System

1. Connect battery to Adafruit Power Switch
   - Red → BAT
   - Black → GND

2. Connect Power Switch to Waveshare UPS HAT
   - OUT → UPS BAT+
   - GND → UPS BAT-

3. Connect UPS HAT to Pi
   - 5V → PP2
   - GND → PP3

4. Add 1000µF capacitor across 5V/GND
   - Negative stripe to GND!

### Step 3: I2C Devices

1. Solder 2.2kΩ pull-ups on SDA/SCL
2. Connect all I2C devices to shared bus
3. Double-check addresses don't conflict

### Step 4: Encoder & Buttons

1. Solder encoder to GPIO5/6/13
2. Add hardware debouncing (100nF + 10kΩ per channel)
3. Connect shutter button to GPIO26

### Step 5: Haptic Driver

1. Connect DRV2605L to I2C bus
2. Add decoupling caps (10µF + 0.1µF)
3. Connect LRA to IN+/IN-
4. Optional: Add 500mA PTC fuse

### Step 6: Testing

```bash
# 1. Test power system
sudo i2cdetect -y 1

# 2. Test camera
libcamera-hello

# 3. Test encoder
python3 hardware/rotary_encoder.py

# 4. Test haptics
python3 hardware/haptic_driver.py

# 5. Run full integration test
pytest tests/test_integration.py
```

---

## 📐 PCB Design Notes (Future)

For a custom PCB version:

1. **Power Plane**
   - Dedicated 5V and 3.3V planes
   - Star-ground topology
   - Multiple decoupling caps near each IC

2. **I2C Bus**
   - Differential pair routing
   - Keep traces <5cm
   - Add series resistors (22Ω-33Ω) for EMI

3. **Encoder**
   - RC filter on-board
   - Optional Schmitt triggers
   - ESD protection diodes

4. **Components**
   - Use 0805 or larger for hand soldering
   - Add test points
   - Labeled silkscreen

---

## 📚 References

- [Raspberry Pi Pinout](https://pinout.xyz/)
- [DRV2605L Datasheet](https://www.ti.com/lit/ds/symlink/drv2605l.pdf)
- [ALPS EC11 Datasheet](https://tech.alpsalpine.com/prod/e/html/encoder/incremental/ec11/ec11_list.html)
- [Adafruit Power Switch Guide](https://learn.adafruit.com/adafruit-power-switch-breakout)
- [I2C Pull-up Calculator](https://www.ti.com/lit/an/slva689/slva689.pdf)

---

*Last updated: 2025-02-11*
*Hardware Revision: 1.0*
