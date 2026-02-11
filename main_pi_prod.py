#!/usr/bin/env python3
"""
SelimCam v6.0 - Production Hardware Code
=========================================

Enterprise-Grade Camera Software für Raspberry Pi 3A+ (512MB RAM)
Multi-Process Architecture mit Zero-Copy IPC

Performance Targets:
- 30 FPS Preview (720p)
- <25ms Input Latency
- <400MB RAM Usage
- 10s Idle → 10 FPS
- 30s Idle → Backlight Off

Hardware:
- Waveshare 4.3" DSI LCD (480x800)
- ALPS EC11 Rotary Encoder
- DRV2605L Haptic Driver + LRA
- IMX219 8MP Camera
- BH1750 Ambient Light Sensor

Author: SelimCam Team
License: MIT
"""

import pygame
import time
import numpy as np
from pathlib import Path
from datetime import datetime
import multiprocessing as mp
import gc
import logging
import sys
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum, auto

# SelimCam Modules
from ipc import IPCManager, SharedFrameBuffer, MessageType, IPCMessage
from camera_service import CameraService, CameraConfig
from rotary_encoder import RotaryEncoder, RotaryDirection
from haptic_driver import HapticController, HapticEffect
from filters import FilterManager

# ==========================================
# LOGGING SETUP
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/var/lib/selimcam/logs/selimcam.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ==========================================
# KONFIGURATION
# ==========================================

# Display (Portrait für DSI LCD)
RES_W, RES_H = 480, 800
FPS_NORMAL = 30
FPS_IDLE = 10
FPS_SLEEP = 1

# Farben (Apple Premium)
COLOR_ACCENT = (255, 204, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_TEXT_GRAY = (160, 160, 160)
COLOR_GLASS_DARK = (0, 0, 0, 180)
COLOR_GLASS_LIGHT = (40, 40, 40, 160)
COLOR_ERROR = (255, 59, 48)
COLOR_SUCCESS = (52, 199, 89)

# Layout
PAD = 20
PILL_RADIUS = 18

# Power Management
IDLE_THRESHOLD_FPS_DROP = 10.0  # Nach 10s → 10 FPS
IDLE_THRESHOLD_BACKLIGHT = 30.0  # Nach 30s → Backlight aus

# Kamera-Parameter
SHUTTER_SPEEDS = ["AUTO", "1/30", "1/60", "1/125", "1/250", "1/500", "1/1000", "1/2000", "1/4000"]
ISO_VALUES = [100, 200, 400, 800, 1600, 3200, 6400]
APERTURES = ["f/2.8", "f/4", "f/5.6", "f/8", "f/11", "f/16"]
FILTER_PRESETS = ["none", "vintage", "bw", "vivid", "portrait"]


# ==========================================
# APP STATE
# ==========================================

class Scene(Enum):
    """App Scenes"""
    CAMERA = auto()
    GALLERY = auto()
    SETTINGS = auto()


@dataclass
class AppState:
    """Zentraler UI State"""
    # Navigation
    scene: Scene = Scene.CAMERA
    
    # Kamera-Parameter
    shutter_idx: int = 4      # 1/250
    iso_idx: int = 3          # 800
    aperture_idx: int = 0     # f/2.8
    filter_idx: int = 0       # none
    
    # UI Animation
    transition_alpha: float = 0.0
    menu_slide_offset: float = 0.0
    
    # Dirty Rect Tracking
    dirty_rects: list = None
    force_full_redraw: bool = True
    
    # Gallery
    gallery_photos: list = None
    gallery_scroll: int = 0
    
    # Settings
    settings_selected: int = 0
    settings_items: list = None
    
    # Power Management
    last_input_time: float = 0.0
    backlight_on: bool = True
    current_fps: int = FPS_NORMAL
    
    # Stats
    frame_count: int = 0
    fps_actual: float = 0.0
    
    def __post_init__(self):
        if self.dirty_rects is None:
            self.dirty_rects = []
        if self.gallery_photos is None:
            self.gallery_photos = []
        if self.settings_items is None:
            self.settings_items = [
                {"label": "Format Card", "value": ""},
                {"label": "Filter", "value": "NONE"},
                {"label": "Grid", "value": "ON"},
                {"label": "Focus Peaking", "value": "ON"},
                {"label": "Haptic Strength", "value": "60%"},
                {"label": "Battery", "value": "94%"},
            ]
    
    def get_current_filter(self) -> str:
        """Aktueller Filter"""
        return FILTER_PRESETS[self.filter_idx]
    
    def register_dirty_rect(self, rect: Tuple[int, int, int, int]):
        """Registriert Dirty Rect für optimiertes Rendering"""
        self.dirty_rects.append(rect)
    
    def clear_dirty_rects(self):
        """Löscht Dirty Rects"""
        self.dirty_rects.clear()


# ==========================================
# HARDWARE PROCESS
# ==========================================

def hardware_process(ipc_manager: IPCManager):
    """
    Hardware-Prozess: GPIO Handling + Haptics
    
    Läuft isoliert um UI nicht zu blockieren.
    Kommuniziert via IPC Events.
    """
    try:
        logger.info("Hardware Process starting...")
        
        # Rotary Encoder Setup
        encoder = RotaryEncoder(
            pin_a=5,
            pin_b=6,
            pin_button=13,
            debounce_ms=2.0,
            long_press_ms=500
        )
        
        # Haptic Controller Setup
        haptic = HapticController(config={
            'i2c_bus': 1,
            'actuator_type': 'LRA',
            'base_amplitude': 0.6,
            'enable_adaptive': True
        })
        
        # Encoder Callbacks
        def on_rotate(direction: int):
            """Encoder Rotation"""
            # Haptic Feedback
            haptic.encoder_detent()
            
            # Send Event to UI
            ipc_manager.send_hw_event('encoder_rotate', direction)
        
        def on_press():
            """Encoder Button Press"""
            haptic.click()
            ipc_manager.send_hw_event('encoder_press', None)
        
        def on_long_press():
            """Encoder Long Press"""
            haptic.success()
            ipc_manager.send_hw_event('encoder_long_press', None)
        
        encoder.on_rotate = on_rotate
        encoder.on_press = on_press
        encoder.on_long_press = on_long_press
        
        logger.info("Hardware Process ready")
        
        # Main Loop: Poll Encoder @ 60Hz
        while True:
            encoder.poll()
            time.sleep(1.0 / 60.0)
    
    except KeyboardInterrupt:
        logger.info("Hardware Process stopping...")
    except Exception as e:
        logger.error(f"Hardware Process error: {e}", exc_info=True)
    finally:
        encoder.cleanup()
        haptic.cleanup()
        logger.info("Hardware Process stopped")


# ==========================================
# CAMERA PROCESS
# ==========================================

def camera_process(ipc_manager: IPCManager):
    """
    Camera-Prozess: Frame Capture + Encoding
    
    Isolierter Prozess für:
    - Live Preview (30 FPS @ 720p)
    - Photo Capture (8MP)
    - Filter Application (Post)
    """
    try:
        logger.info("Camera Process starting...")
        
        # Camera Config
        config = CameraConfig(
            preview_width=640,
            preview_height=480,
            preview_fps=30,
            capture_width=3280,
            capture_height=2464,
            capture_quality=95
        )
        
        # Camera Service
        camera = CameraService(config)
        camera.start_preview()
        
        filter_manager = FilterManager()
        current_filter = "none"
        
        logger.info("Camera Process ready")
        
        # Stats
        frame_times = []
        last_stats_time = time.perf_counter()
        
        while True:
            frame_start = time.perf_counter()
            
            # Capture Frame
            frame = camera.capture_array()
            
            if frame is not None:
                # Apply Live Filter (fast!)
                if current_filter != "none":
                    frame = filter_manager.apply_preset(frame, current_filter)
                
                # Write to Shared Memory (Zero-Copy!)
                ipc_manager.frame_buffer.write_frame(frame)
                
                # Notify UI
                ipc_manager.send_frame_ready()
                
                # Stats
                frame_time = time.perf_counter() - frame_start
                frame_times.append(frame_time)
                
                if len(frame_times) > 30:
                    frame_times.pop(0)
                
                # Log Stats every 5s
                if time.perf_counter() - last_stats_time > 5.0:
                    avg_time = np.mean(frame_times) * 1000
                    fps = 1.0 / np.mean(frame_times)
                    logger.info(f"Camera: {fps:.1f} FPS, {avg_time:.1f}ms/frame")
                    last_stats_time = time.perf_counter()
            
            # Target: 30 FPS
            elapsed = time.perf_counter() - frame_start
            sleep_time = max(0, (1.0 / 30.0) - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    except KeyboardInterrupt:
        logger.info("Camera Process stopping...")
    except Exception as e:
        logger.error(f"Camera Process error: {e}", exc_info=True)
    finally:
        camera.stop()
        logger.info("Camera Process stopped")


# ==========================================
# RENDERING (OPTIMIERT)
# ==========================================

class Renderer:
    """
    Optimierter Renderer mit Dirty Rect Support
    
    Strategien:
    - Full Redraw nur bei Szenen-Wechsel
    - Dirty Rects für UI-Updates
    - Surface Caching für statische Elemente
    """
    
    def __init__(self, screen: pygame.Surface, fonts: dict):
        self.screen = screen
        self.fonts = fonts
        
        # Surface Cache
        self.cached_bg = None
        self.cached_ui_elements = {}
        
        # Filter Manager
        self.filter_manager = FilterManager()
    
    def draw_pill(self, rect: Tuple[int, int, int, int], color, radius=PILL_RADIUS):
        """Zeichnet Pille"""
        shape_surf = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        pygame.draw.rect(shape_surf, color, shape_surf.get_rect(), border_radius=radius)
        self.screen.blit(shape_surf, (rect[0], rect[1]))
    
    def draw_text_center(self, font, text: str, color, center_xy):
        """Zentrierter Text"""
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=center_xy)
        self.screen.blit(surf, rect)
        return rect
    
    def draw_text_left(self, font, text: str, color, left_xy):
        """Linksbündiger Text"""
        surf = font.render(text, True, color)
        rect = surf.get_rect(topleft=left_xy)
        self.screen.blit(surf, rect)
        return rect
    
    def render_camera_view(self, state: AppState, viewfinder_frame: Optional[np.ndarray]):
        """Kamera-Ansicht"""
        center_x = RES_W // 2
        
        # 1. Viewfinder (direkt aus Shared Memory - Zero Copy!)
        if viewfinder_frame is not None:
            # NumPy → pygame Surface (fast!)
            # Frame ist (H, W, C) -> muss transponiert werden
            frame_transposed = np.transpose(viewfinder_frame, (1, 0, 2))
            surf = pygame.surfarray.make_surface(frame_transposed)
            surf = pygame.transform.scale(surf, (RES_W, RES_H))
            self.screen.blit(surf, (0, 0))
        else:
            # Fallback
            self.screen.fill((30, 30, 30))
        
        # 2. Top Bar
        self.draw_pill((0, 0, RES_W, 60), (0, 0, 0, 120), radius=0)
        
        # Modus
        self.draw_pill((PAD, 12, 90, 36), COLOR_GLASS_LIGHT, radius=10)
        self.draw_text_center(self.fonts['s'], "MANUAL", COLOR_ACCENT, (PAD + 45, 30))
        
        # Filter Badge
        filter_name = state.get_current_filter().upper()
        if filter_name != "NONE":
            self.draw_pill((center_x - 60, 12, 120, 36), COLOR_GLASS_DARK, radius=10)
            self.draw_text_center(self.fonts['xs'], filter_name, COLOR_ACCENT, (center_x, 30))
        
        # Batterie
        battery_x = RES_W - PAD - 30
        self.draw_text_center(self.fonts['m'], "94%", COLOR_WHITE, (battery_x, 22))
        self.draw_text_center(self.fonts['xs'], "RAW+J", COLOR_TEXT_GRAY, (battery_x, 40))
        
        # 3. Focus Peaking
        pygame.draw.circle(self.screen, (255, 255, 255, 80), (center_x, RES_H // 2), 3)
        pygame.draw.circle(self.screen, (255, 255, 255, 40), (center_x, RES_H // 2), 40, 1)
        
        # 4. Bottom Controls
        main_pill_h = 90
        main_pill_y = RES_H - main_pill_h - PAD
        self.draw_pill((PAD, main_pill_y, RES_W - 2*PAD, main_pill_h), COLOR_GLASS_DARK, radius=25)
        
        shutter_val = SHUTTER_SPEEDS[state.shutter_idx]
        self.draw_text_center(self.fonts['xl'], shutter_val, COLOR_WHITE, (center_x, main_pill_y + 35))
        self.draw_text_center(self.fonts['s'], "SHUTTER SPEED", COLOR_TEXT_GRAY, (center_x, main_pill_y + 70))
        
        # ISO & Aperture
        sec_pill_h = 60
        sec_pill_y = main_pill_y - sec_pill_h - 15
        pill_w = (RES_W - 2*PAD - 15) // 2
        
        self.draw_pill((PAD, sec_pill_y, pill_w, sec_pill_h), COLOR_GLASS_DARK, radius=20)
        iso_val = str(ISO_VALUES[state.iso_idx])
        self.draw_text_center(self.fonts['l'], iso_val, COLOR_WHITE, (PAD + pill_w//2, sec_pill_y + 25))
        self.draw_text_center(self.fonts['s'], "ISO", COLOR_TEXT_GRAY, (PAD + pill_w//2, sec_pill_y + 48))
        
        self.draw_pill((RES_W - PAD - pill_w, sec_pill_y, pill_w, sec_pill_h), COLOR_GLASS_DARK, radius=20)
        aperture_val = APERTURES[state.aperture_idx]
        self.draw_text_center(self.fonts['l'], aperture_val, COLOR_ACCENT, 
                            (RES_W - PAD - pill_w//2, sec_pill_y + 25))
        self.draw_text_center(self.fonts['s'], "APERTURE", COLOR_TEXT_GRAY, 
                            (RES_W - PAD - pill_w//2, sec_pill_y + 48))
        
        # 5. FPS Counter (Debug)
        fps_text = f"{state.fps_actual:.1f} FPS"
        self.draw_text_left(self.fonts['xs'], fps_text, COLOR_TEXT_GRAY, (10, RES_H - 20))
    
    def render_gallery_view(self, state: AppState):
        """Galerie (Optimiert mit Dirty Rects)"""
        if state.force_full_redraw:
            self.screen.fill((15, 15, 15))
            
            # Header
            self.draw_text_center(self.fonts['l'], "Gallery", COLOR_WHITE, (RES_W//2, 50))
            self.draw_text_center(self.fonts['xs'], f"{len(state.gallery_photos)} photos", 
                                COLOR_TEXT_GRAY, (RES_W//2, 75))
            
            # Grid
            # TODO: Implement thumbnail grid
            
            # Footer
            self.draw_text_center(self.fonts['s'], "Encoder: Select  Press: View", 
                                COLOR_TEXT_GRAY, (RES_W//2, RES_H - 40))
        
        else:
            # Nur Dirty Rects updaten
            pass
    
    def render_settings_overlay(self, state: AppState):
        """Settings mit Animation"""
        # Blur Overlay
        overlay = pygame.Surface((RES_W, RES_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 230))
        self.screen.blit(overlay, (0, 0))
        
        # Slide Animation
        offset_y = int(state.menu_slide_offset)
        
        # Titel
        self.draw_text_center(self.fonts['xl'], "Settings", COLOR_WHITE, (RES_W//2, 80 + offset_y))
        
        # Items
        btn_h = 55
        start_y = 160
        
        for i, item in enumerate(state.settings_items):
            y_pos = start_y + i * (btn_h + 15) + offset_y
            
            if y_pos < -btn_h or y_pos > RES_H:
                continue  # Außerhalb sichtbar
            
            is_selected = (i == state.settings_selected)
            pill_color = COLOR_GLASS_LIGHT if is_selected else (50, 50, 50)
            self.draw_pill((PAD, y_pos, RES_W - 2*PAD, btn_h), pill_color, radius=18)
            
            self.draw_text_left(self.fonts['m'], item['label'], COLOR_WHITE, 
                              (PAD + 20, y_pos + btn_h//2 - 10))
            
            if item['value']:
                val_surf = self.fonts['m'].render(item['value'], True, COLOR_ACCENT)
                val_rect = val_surf.get_rect(midright=(RES_W - PAD - 20, y_pos + btn_h//2))
                self.screen.blit(val_surf, val_rect)
        
        # Footer
        self.draw_text_center(self.fonts['s'], "Encoder: Navigate  Long Press: Exit", 
                            COLOR_TEXT_GRAY, (RES_W//2, RES_H - 50))


# ==========================================
# INPUT HANDLER
# ==========================================

class InputHandler:
    """Verarbeitet Hardware-Events"""
    
    def __init__(self, state: AppState, ipc_manager: IPCManager):
        self.state = state
        self.ipc = ipc_manager
    
    def handle_encoder_rotate(self, direction: int):
        """Encoder Rotation"""
        self.state.last_input_time = time.perf_counter()
        
        if self.state.scene == Scene.CAMERA:
            # Shutter Speed
            if direction > 0:
                self.state.shutter_idx = (self.state.shutter_idx + 1) % len(SHUTTER_SPEEDS)
            else:
                self.state.shutter_idx = (self.state.shutter_idx - 1) % len(SHUTTER_SPEEDS)
            
            self.state.register_dirty_rect((0, RES_H - 200, RES_W, 200))
        
        elif self.state.scene == Scene.SETTINGS:
            # Settings Navigation
            if direction > 0:
                self.state.settings_selected = min(
                    len(self.state.settings_items) - 1, 
                    self.state.settings_selected + 1
                )
            else:
                self.state.settings_selected = max(0, self.state.settings_selected - 1)
            
            self.state.force_full_redraw = True
    
    def handle_encoder_press(self):
        """Encoder Button Press"""
        self.state.last_input_time = time.perf_counter()
        
        if self.state.scene == Scene.CAMERA:
            # Toggle Filter
            self.state.filter_idx = (self.state.filter_idx + 1) % len(FILTER_PRESETS)
            self.state.settings_items[1]['value'] = self.state.get_current_filter().upper()
            self.state.force_full_redraw = True
        
        elif self.state.scene == Scene.GALLERY:
            # View Photo
            pass
    
    def handle_encoder_long_press(self):
        """Encoder Long Press"""
        self.state.last_input_time = time.perf_counter()
        
        # Toggle Settings
        if self.state.scene == Scene.SETTINGS:
            self.state.scene = Scene.CAMERA
            self.state.menu_slide_offset = 200  # Start animation
        else:
            self.state.scene = Scene.SETTINGS
            self.state.menu_slide_offset = 200
        
        self.state.force_full_redraw = True
    
    def poll_hardware_events(self):
        """Poll IPC Events von Hardware-Process"""
        events = self.ipc.poll_hw_events()
        
        for msg in events:
            if msg.type == MessageType.ENCODER_EVENT:
                event_type = msg.data['type']
                event_data = msg.data['data']
                
                if event_type == 'encoder_rotate':
                    self.handle_encoder_rotate(event_data)
                elif event_type == 'encoder_press':
                    self.handle_encoder_press()
                elif event_type == 'encoder_long_press':
                    self.handle_encoder_long_press()


# ==========================================
# POWER MANAGEMENT
# ==========================================

class PowerManager:
    """Verwaltet Power-States"""
    
    def __init__(self, state: AppState):
        self.state = state
    
    def update(self):
        """Update Power State"""
        idle_time = time.perf_counter() - self.state.last_input_time
        
        # FPS-Drosselung
        if idle_time > IDLE_THRESHOLD_FPS_DROP:
            self.state.current_fps = FPS_IDLE
        else:
            self.state.current_fps = FPS_NORMAL
        
        # Backlight
        if idle_time > IDLE_THRESHOLD_BACKLIGHT:
            if self.state.backlight_on:
                self.state.backlight_on = False
                logger.info("Power: Backlight OFF")
                # TODO: GPIO Backlight Pin Low
        else:
            if not self.state.backlight_on:
                self.state.backlight_on = True
                logger.info("Power: Backlight ON")
                # TODO: GPIO Backlight Pin High


# ==========================================
# UI PROCESS (MAIN)
# ==========================================

def ui_process():
    """
    UI-Prozess: Rendering + Input + Power Management
    
    Dies ist der Haupt-Prozess.
    """
    try:
        logger.info("UI Process starting...")
        
        # Pygame Init
        pygame.init()
        screen = pygame.display.set_mode((RES_W, RES_H), pygame.FULLSCREEN)
        pygame.display.set_caption("SelimCam v6.0")
        pygame.mouse.set_visible(False)
        clock = pygame.time.Clock()
        
        # Fonts
        try:
            fonts = {
                'xl': pygame.font.Font("static/inter_bold.ttf", 42),
                'l': pygame.font.Font("static/inter_bold.ttf", 26),
                'm': pygame.font.Font("static/inter_regular.ttf", 18),
                's': pygame.font.Font("static/inter_regular.ttf", 14),
                'xs': pygame.font.Font("static/inter_regular.ttf", 12),
            }
        except:
            logger.warning("Inter Font nicht gefunden, nutze System-Font")
            sys_font = pygame.font.SysFont("Arial", 20, bold=True)
            fonts = {'xl': sys_font, 'l': sys_font, 'm': sys_font, 's': sys_font, 'xs': sys_font}
        
        # IPC Setup
        ipc = IPCManager('ui')
        
        # App State
        state = AppState()
        state.last_input_time = time.perf_counter()
        
        # Scan Photos
        photo_dir = Path("/var/lib/selimcam/photos")
        photo_dir.mkdir(parents=True, exist_ok=True)
        state.gallery_photos = sorted(photo_dir.glob("IMG_*.jpg"))
        logger.info(f"Found {len(state.gallery_photos)} photos in gallery")
        
        # Renderer
        renderer = Renderer(screen, fonts)
        
        # Input Handler
        input_handler = InputHandler(state, ipc)
        
        # Power Manager
        power_mgr = PowerManager(state)
        
        logger.info("UI Process ready")
        
        # Stats
        frame_times = []
        last_stats_time = time.perf_counter()
        
        # Main Loop
        running = True
        while running:
            frame_start = time.perf_counter()
            
            # 1. Poll Hardware Events
            input_handler.poll_hardware_events()
            
            # 2. Update Power State
            power_mgr.update()
            
            # 3. Get Viewfinder Frame (Zero-Copy!)
            viewfinder_frame = ipc.frame_buffer.read_frame()
            
            # 4. Render
            if state.force_full_redraw or state.scene == Scene.CAMERA:
                # Full Redraw
                if state.scene == Scene.CAMERA:
                    renderer.render_camera_view(state, viewfinder_frame)
                elif state.scene == Scene.GALLERY:
                    renderer.render_gallery_view(state)
                elif state.scene == Scene.SETTINGS:
                    renderer.render_camera_view(state, viewfinder_frame)
                    renderer.render_settings_overlay(state)
                
                pygame.display.flip()
                state.force_full_redraw = False
            
            elif len(state.dirty_rects) > 0:
                # Dirty Rect Update (Settings/Gallery Only)
                pygame.display.update(state.dirty_rects)
                state.clear_dirty_rects()
            
            # 5. Update Animations
            if state.menu_slide_offset > 0:
                state.menu_slide_offset = max(0, state.menu_slide_offset - 20)
                state.force_full_redraw = True
            
            # 6. FPS Stats
            frame_time = time.perf_counter() - frame_start
            frame_times.append(frame_time)
            if len(frame_times) > 30:
                frame_times.pop(0)
            
            state.fps_actual = 1.0 / np.mean(frame_times)
            state.frame_count += 1
            
            # Log Stats
            if time.perf_counter() - last_stats_time > 10.0:
                avg_time = np.mean(frame_times) * 1000
                logger.info(f"UI: {state.fps_actual:.1f} FPS, {avg_time:.1f}ms/frame, "
                          f"Scene={state.scene.name}, FPS_Target={state.current_fps}")
                last_stats_time = time.perf_counter()
                
                # Garbage Collection bei Szenen-Wechsel
                if state.scene != Scene.CAMERA:
                    collected = gc.collect()
                    logger.debug(f"GC: Collected {collected} objects")
            
            # 7. Frame Limit (adaptiv)
            elapsed = time.perf_counter() - frame_start
            sleep_time = max(0, (1.0 / state.current_fps) - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
        
    except KeyboardInterrupt:
        logger.info("UI Process stopping...")
    except Exception as e:
        logger.error(f"UI Process error: {e}", exc_info=True)
    finally:
        pygame.quit()
        ipc.cleanup()
        logger.info("UI Process stopped")


# ==========================================
# MAIN ENTRY POINT
# ==========================================

def main():
    """
    SelimCam Main Entry Point
    
    Startet Multi-Process Architektur:
    1. Camera Process (Frame Capture)
    2. Hardware Process (GPIO/Haptics)
    3. UI Process (Rendering) <- Main
    """
    logger.info("="*60)
    logger.info("SelimCam v6.0 Starting...")
    logger.info("="*60)
    
    # IPC Setup (shared zwischen Prozessen)
    # Muss VOR fork() erstellt werden
    ipc = IPCManager('camera')
    
    # Starte Subprozesse
    p_camera = mp.Process(target=camera_process, args=(ipc,), name="CameraProcess")
    p_hardware = mp.Process(target=hardware_process, args=(ipc,), name="HardwareProcess")
    
    p_camera.start()
    p_hardware.start()
    
    logger.info(f"Camera Process PID: {p_camera.pid}")
    logger.info(f"Hardware Process PID: {p_hardware.pid}")
    
    # UI läuft im Main Process
    try:
        ui_process()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    finally:
        # Cleanup
        logger.info("Shutting down subprocesses...")
        
        p_camera.terminate()
        p_hardware.terminate()
        
        p_camera.join(timeout=5)
        p_hardware.join(timeout=5)
        
        if p_camera.is_alive():
            p_camera.kill()
        if p_hardware.is_alive():
            p_hardware.kill()
        
        logger.info("SelimCam stopped")


if __name__ == "__main__":
    # Multiprocessing Setup für spawn (sicherer auf Linux)
    mp.set_start_method('spawn', force=True)
    
    main()
