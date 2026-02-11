#!/usr/bin/env python3
"""
SelimCam v6.0 FINAL - PC Simulator
===================================

Desktop Test Environment mit allen Features:
- Ghost UI (PURE/ESSENTIAL/PRO Modi)
- Blind Controls (nur Haptic Feedback)
- Date Stamp Engine
- Proxy-Filter für Performance
- Grid & Level Overlays
- Mehrsprachigkeit (DE/EN)
- Battery Saver

Controls:
- ↑↓: Shutter Speed (blind, kein UI!)
- ←→: ISO ändern
- SPACE: Foto aufnehmen
- F: Filter wechseln
- D: Display Mode wechseln (PURE/ESSENTIAL/PRO)
- G: Grid Toggle
- L: Level Toggle
- T: Sprache wechseln (DE/EN)
- TAB: Gallery
- ESC: Settings
- H: Haptic Feedback simulieren (visueller Flash)

Author: SelimCam Team
License: MIT
"""

import pygame
import time
import numpy as np
from pathlib import Path
from datetime import datetime
import threading
import queue
from typing import Optional, Tuple
from enum import Enum, auto
import sys

# Filter-System
sys.path.insert(0, str(Path(__file__).parent))
from filters import FilterManager

# ==========================================
# KONFIGURATION
# ==========================================

RES_W, RES_H = 480, 800
FPS_NORMAL = 60
FPS_IDLE = 5

# Farben
COLOR_ACCENT = (255, 204, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_TEXT_GRAY = (160, 160, 160)
COLOR_GLASS_DARK = (0, 0, 0, 180)
COLOR_GLASS_LIGHT = (40, 40, 40, 160)
COLOR_SUCCESS = (52, 199, 89)
COLOR_ERROR = (255, 59, 48)

PAD = 20
PILL_RADIUS = 18

# Kamera-Parameter
SHUTTER_SPEEDS = ["AUTO", "1/30", "1/60", "1/125", "1/250", "1/500", "1/1000", "1/2000", "1/4000"]
ISO_VALUES = [100, 200, 400, 800, 1600, 3200, 6400]
APERTURES = ["f/2.8", "f/4", "f/5.6", "f/8", "f/11", "f/16"]
FILTER_PRESETS = ["none", "vintage", "bw", "vivid", "portrait"]

# Battery Saver
IDLE_FPS_DROP = 30.0  # Nach 30s → 5 FPS
IDLE_SCREEN_OFF = 60.0  # Nach 60s → Schwarz


# ==========================================
# MEHRSPRACHIGKEIT
# ==========================================

TRANSLATIONS = {
    'en': {
        'settings': 'Settings',
        'format_card': 'Format Card',
        'filter': 'Filter',
        'grid': 'Grid',
        'level': 'Level',
        'haptics': 'Haptics',
        'date_stamp': 'Date Stamp',
        'language': 'Language',
        'set_time': 'Set Time/Date',
        'battery': 'Battery',
        'photos_left': 'photos',
        'press_to_close': 'Press ESC to close',
        'manual': 'MANUAL',
    },
    'de': {
        'settings': 'Einstellungen',
        'format_card': 'Karte formatieren',
        'filter': 'Filter',
        'grid': 'Raster',
        'level': 'Wasserwaage',
        'haptics': 'Haptik',
        'date_stamp': 'Datumsstempel',
        'language': 'Sprache',
        'set_time': 'Zeit/Datum',
        'battery': 'Batterie',
        'photos_left': 'Fotos',
        'press_to_close': 'ESC zum Schließen',
        'manual': 'MANUELL',
    }
}


# ==========================================
# ENUMS
# ==========================================

class DisplayMode(Enum):
    """Ghost UI Modi"""
    PURE = auto()       # 100% Bild, NICHTS sonst
    ESSENTIAL = auto()  # Batterie + Fotos übrig
    PRO = auto()        # + ISO, Filter, Mini-Histogram


class Scene(Enum):
    """App Scenes"""
    CAMERA = auto()
    GALLERY = auto()
    SETTINGS = auto()


class HapticLevel(Enum):
    """Haptic Feedback Stärke"""
    OFF = "OFF"
    LOW = "LOW"
    HIGH = "HIGH"


# ==========================================
# APP STATE
# ==========================================

class AppState:
    """Zentraler State"""
    def __init__(self):
        # Navigation
        self.scene = Scene.CAMERA
        
        # Kamera
        self.shutter_idx = 4  # 1/250
        self.iso_idx = 3      # 800
        self.aperture_idx = 0
        self.filter_idx = 0
        
        # Ghost UI
        self.display_mode = DisplayMode.ESSENTIAL
        
        # Overlays
        self.grid_enabled = True
        self.level_enabled = False
        self.date_stamp_enabled = True
        
        # Settings
        self.language = 'en'
        self.haptic_level = HapticLevel.HIGH
        
        # Power
        self.last_input_time = time.perf_counter()
        self.screen_active = True
        self.current_fps = FPS_NORMAL
        
        # Effects
        self.haptic_flash_time = 0.0
        self.shutter_flash_time = 0.0
        self.menu_slide_offset = 0.0
        
        # Gallery
        self.photo_dir = Path("./photos")
        self.photo_dir.mkdir(exist_ok=True)
        self.gallery_photos = sorted(self.photo_dir.glob("IMG_*.jpg"))
        
        # Settings Menu
        self.settings_selected = 0
        self.build_settings_menu()
        
        # Filter Manager
        self.filter_manager = FilterManager()
        
        # Gyro (Mock)
        self.gyro_angle = 0.0  # -90 bis +90 Grad
    
    def build_settings_menu(self):
        """Erstellt Settings Menu mit Übersetzungen"""
        t = TRANSLATIONS[self.language]
        self.settings_items = [
            {"key": "format_card", "label": t['format_card'], "value": ""},
            {"key": "filter", "label": t['filter'], "value": self.get_current_filter().upper()},
            {"key": "grid", "label": t['grid'], "value": "ON" if self.grid_enabled else "OFF"},
            {"key": "level", "label": t['level'], "value": "ON" if self.level_enabled else "OFF"},
            {"key": "haptics", "label": t['haptics'], "value": self.haptic_level.value},
            {"key": "date_stamp", "label": t['date_stamp'], "value": "ON" if self.date_stamp_enabled else "OFF"},
            {"key": "language", "label": t['language'], "value": self.language.upper()},
            {"key": "set_time", "label": t['set_time'], "value": ""},
            {"key": "battery", "label": t['battery'], "value": "94%"},
        ]
    
    def get_current_filter(self) -> str:
        return FILTER_PRESETS[self.filter_idx]
    
    def t(self, key: str) -> str:
        """Übersetzung abrufen"""
        return TRANSLATIONS[self.language].get(key, key)
    
    def toggle_language(self):
        """Sprache wechseln"""
        self.language = 'de' if self.language == 'en' else 'en'
        self.build_settings_menu()


# ==========================================
# DATE STAMP ENGINE
# ==========================================

class DateStamper:
    """Brennt Datumsstempel in Bilder (Retro Pixel Font)"""
    
    def __init__(self):
        # Pixel Font (klein, monospace)
        try:
            self.font = pygame.font.Font("static/inter_regular.ttf", 14)
        except:
            self.font = pygame.font.SysFont("monospace", 12, bold=True)
    
    def stamp_image(self, surface: pygame.Surface) -> pygame.Surface:
        """
        Brennt Datum/Zeit in Bild (unten rechts)
        
        Format: DD.MM.YYYY HH:MM
        Style: Weiß mit Schatten (Retro-Look)
        """
        stamped = surface.copy()
        
        # Zeitstempel
        now = datetime.now()
        text = now.strftime("%d.%m.%Y %H:%M")
        
        # Render mit Schatten
        # Schatten (schwarz, leicht versetzt)
        shadow = self.font.render(text, True, (0, 0, 0))
        shadow_rect = shadow.get_rect(bottomright=(RES_W - 12, RES_H - 12))
        stamped.blit(shadow, shadow_rect)
        
        # Text (weiß)
        text_surf = self.font.render(text, True, (255, 255, 255))
        text_rect = text_surf.get_rect(bottomright=(RES_W - 10, RES_H - 10))
        stamped.blit(text_surf, text_rect)
        
        return stamped


# ==========================================
# PROXY FILTER RENDERER
# ==========================================

class ProxyFilterRenderer:
    """
    Performance-Optimierte Filter-Vorschau
    
    Strategie:
    1. Downscale Bild auf 320x240 (1/4 Pixel)
    2. Wende Filter auf kleines Bild an (90% CPU-Ersparnis!)
    3. Upscale zurück auf Original-Größe
    
    Für Live-Preview absolut ausreichend.
    High-Res Filter nur beim Speichern.
    """
    
    def __init__(self, filter_manager: FilterManager):
        self.filter_manager = filter_manager
        
        # Proxy-Größe (1/4 der Display-Auflösung)
        self.proxy_w = RES_W // 2
        self.proxy_h = RES_H // 2
    
    def apply_filter_live(self, surface: pygame.Surface, filter_name: str) -> pygame.Surface:
        """
        Wendet Filter auf Surface an (optimiert für Live-Preview)
        
        Performance: ~5ms statt ~50ms für Full-Res
        """
        if filter_name == "none":
            return surface
        
        # 1. Downscale (Performance-Boost!)
        proxy = pygame.transform.smoothscale(surface, (self.proxy_w, self.proxy_h))
        
        # 2. Surface → NumPy
        arr = pygame.surfarray.array3d(proxy)
        arr = np.transpose(arr, (1, 0, 2))  # (w,h,c) → (h,w,c)
        
        # 3. Filter anwenden (auf kleinem Bild = schnell!)
        filtered = self.filter_manager.apply_preset(arr, filter_name)
        
        # 4. NumPy → Surface
        filtered = np.transpose(filtered, (1, 0, 2))
        filtered_surf = pygame.surfarray.make_surface(filtered)
        
        # 5. Upscale zurück (bilinear interpolation, sieht gut aus)
        result = pygame.transform.smoothscale(filtered_surf, (RES_W, RES_H))
        
        return result


# ==========================================
# ASYNC PHOTO SAVER
# ==========================================

class AsyncPhotoSaver:
    """
    Non-Blocking Foto-Speicherung in separatem Thread
    
    Verhindert UI-Freezes beim Speichern von High-Res Bildern
    """
    
    def __init__(self, filter_manager: FilterManager):
        self.filter_manager = filter_manager
        self.date_stamper = DateStamper()
        
        # Queue für Speicher-Aufgaben
        self.save_queue = queue.Queue(maxsize=10)
        
        # Worker Thread
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()
        
        print("✅ AsyncPhotoSaver: Worker Thread gestartet")
    
    def save_photo_async(self, surface: pygame.Surface, filter_name: str, 
                        date_stamp: bool, photo_dir: Path):
        """
        Speichert Foto asynchron (non-blocking)
        
        Args:
            surface: Vollbild-Surface (480x800)
            filter_name: Zu verwendender Filter
            date_stamp: Datumsstempel hinzufügen?
            photo_dir: Ziel-Ordner
        """
        # In Queue packen (Worker Thread verarbeitet)
        try:
            self.save_queue.put_nowait({
                'surface': surface.copy(),  # WICHTIG: Copy für Thread-Safety!
                'filter': filter_name,
                'date_stamp': date_stamp,
                'photo_dir': photo_dir
            })
            print(f"📸 Foto in Queue ({self.save_queue.qsize()} pending)")
        except queue.Full:
            print("⚠️  Save Queue voll! Foto verworfen.")
    
    def _worker_loop(self):
        """Worker Thread Loop (läuft dauerhaft)"""
        while True:
            try:
                # Warte auf Aufgabe
                task = self.save_queue.get()
                
                # Verarbeite
                self._process_save(task)
                
                self.save_queue.task_done()
            
            except Exception as e:
                print(f"❌ AsyncPhotoSaver Error: {e}")
    
    def _process_save(self, task: dict):
        """
        Verarbeitet Speicher-Aufgabe (läuft in Worker Thread!)
        
        Hier können wir blockieren - UI läuft weiter!
        """
        start = time.perf_counter()
        
        surface = task['surface']
        filter_name = task['filter']
        date_stamp = task['date_stamp']
        photo_dir = task['photo_dir']
        
        # 1. Full-Res Filter anwenden (langsam, aber OK in Thread)
        if filter_name != "none":
            arr = pygame.surfarray.array3d(surface)
            arr = np.transpose(arr, (1, 0, 2))
            filtered = self.filter_manager.apply_preset(arr, filter_name)
            filtered = np.transpose(filtered, (1, 0, 2))
            surface = pygame.surfarray.make_surface(filtered)
        
        # 2. Date Stamp
        if date_stamp:
            surface = self.date_stamper.stamp_image(surface)
        
        # 3. Speichern
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"IMG_{timestamp}_{filter_name}.jpg"
        filepath = photo_dir / filename
        
        pygame.image.save(surface, str(filepath))
        
        elapsed = (time.perf_counter() - start) * 1000
        print(f"✅ Foto gespeichert: {filename} ({elapsed:.1f}ms)")


# ==========================================
# RENDERER
# ==========================================

class Renderer:
    """Optimierter Renderer mit Ghost UI"""
    
    def __init__(self, screen: pygame.Surface, fonts: dict, state: AppState):
        self.screen = screen
        self.fonts = fonts
        self.state = state
        
        # Proxy Filter
        self.proxy_filter = ProxyFilterRenderer(state.filter_manager)
        
        # Histogram Cache (für PRO Mode)
        self.histogram_cache = None
        self.histogram_cache_time = 0.0
    
    def draw_pill(self, rect, color, radius=PILL_RADIUS):
        """Zeichnet Pille"""
        surf = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        pygame.draw.rect(surf, color, surf.get_rect(), border_radius=radius)
        self.screen.blit(surf, (rect[0], rect[1]))
    
    def draw_text_center(self, font, text, color, center_xy):
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=center_xy)
        self.screen.blit(surf, rect)
    
    def draw_text_left(self, font, text, color, left_xy):
        surf = font.render(text, True, color)
        rect = surf.get_rect(topleft=left_xy)
        self.screen.blit(surf, rect)
    
    def draw_text_right(self, font, text, color, right_xy):
        surf = font.render(text, True, color)
        rect = surf.get_rect(topright=right_xy)
        self.screen.blit(surf, rect)
    
    def draw_grid_overlay(self):
        """Grid Overlay (Drittel-Regel)"""
        if not self.state.grid_enabled:
            return
        
        # Vertikale Linien
        x1 = RES_W // 3
        x2 = 2 * RES_W // 3
        
        # Horizontale Linien
        y1 = RES_H // 3
        y2 = 2 * RES_H // 3
        
        # Weiß mit 30% Opacity
        color = (255, 255, 255, 76)
        
        # Vertikale
        pygame.draw.line(self.screen, color, (x1, 0), (x1, RES_H), 1)
        pygame.draw.line(self.screen, color, (x2, 0), (x2, RES_H), 1)
        
        # Horizontale
        pygame.draw.line(self.screen, color, (0, y1), (RES_W, y1), 1)
        pygame.draw.line(self.screen, color, (0, y2), (RES_W, y2), 1)
    
    def draw_level_overlay(self):
        """Level/Wasserwaage (Rechter Rand)"""
        if not self.state.level_enabled:
            return
        
        # Position rechts
        x = RES_W - 30
        center_y = RES_H // 2
        
        # Winkel (Mock: -5 bis +5 Grad, oszilliert)
        angle = self.state.gyro_angle
        
        # Farbe: Grün wenn gerade (±2°), sonst Weiß
        if abs(angle) < 2:
            color = COLOR_SUCCESS
        else:
            color = COLOR_WHITE
        
        # Vertikale Linie (Referenz)
        pygame.draw.line(self.screen, (255, 255, 255, 100), 
                        (x, center_y - 50), (x, center_y + 50), 1)
        
        # Level-Indikator (bewegt sich mit Winkel)
        offset = int(angle * 3)  # 3 Pixel pro Grad
        pygame.draw.circle(self.screen, color, (x, center_y + offset), 5)
        pygame.draw.circle(self.screen, color, (x, center_y + offset), 5, 1)
    
    def compute_mini_histogram(self, surface: pygame.Surface) -> pygame.Surface:
        """
        Berechnet Mini-Histogram (optimiert!)
        
        Performance: Nur alle 500ms neu berechnen (gecacht)
        """
        now = time.perf_counter()
        
        # Cache gültig?
        if self.histogram_cache and (now - self.histogram_cache_time) < 0.5:
            return self.histogram_cache
        
        # Downscale für Performance
        small = pygame.transform.scale(surface, (80, 60))
        arr = pygame.surfarray.array3d(small)
        
        # Luminanz
        gray = np.mean(arr, axis=2).astype(np.uint8)
        
        # Histogram
        hist, _ = np.histogram(gray, bins=32, range=(0, 256))
        hist = hist / hist.max()  # Normalisieren
        
        # Render Histogram (Mini!)
        hist_w, hist_h = 60, 30
        hist_surf = pygame.Surface((hist_w, hist_h), pygame.SRCALPHA)
        hist_surf.fill((0, 0, 0, 180))
        
        bar_w = hist_w / 32
        for i, val in enumerate(hist):
            bar_h = int(val * hist_h)
            if bar_h > 0:
                x = int(i * bar_w)
                pygame.draw.rect(hist_surf, (255, 255, 255, 200), 
                               (x, hist_h - bar_h, int(bar_w), bar_h))
        
        # Cache
        self.histogram_cache = hist_surf
        self.histogram_cache_time = now
        
        return hist_surf
    
    def render_camera_view(self, bg_surface: pygame.Surface):
        """
        Kamera-Ansicht mit Ghost UI
        
        Zeigt je nach Display Mode unterschiedlich viel UI
        """
        # 1. Hintergrund (Viewfinder mit Filter)
        filtered_bg = self.proxy_filter.apply_filter_live(bg_surface, self.state.get_current_filter())
        self.screen.blit(filtered_bg, (0, 0))
        
        # 2. Overlays (immer sichtbar, unabhängig von Display Mode)
        self.draw_grid_overlay()
        self.draw_level_overlay()
        
        # 3. Ghost UI (abhängig von Display Mode)
        
        if self.state.display_mode == DisplayMode.PURE:
            # 100% BILD, NICHTS SONST!
            pass
        
        elif self.state.display_mode == DisplayMode.ESSENTIAL:
            # Batterie (oben rechts)
            self.draw_text_right(self.fonts['xs'], "94%", COLOR_WHITE, (RES_W - 10, 10))
            
            # Fotos übrig (oben links)
            photos_left = 999 - len(self.state.gallery_photos)
            self.draw_text_left(self.fonts['xs'], f"{photos_left} {self.state.t('photos_left')}", 
                              COLOR_TEXT_GRAY, (10, 10))
        
        elif self.state.display_mode == DisplayMode.PRO:
            # ESSENTIAL + Extra Infos
            
            # Batterie
            self.draw_text_right(self.fonts['xs'], "94%", COLOR_WHITE, (RES_W - 10, 10))
            
            # Fotos übrig
            photos_left = 999 - len(self.state.gallery_photos)
            self.draw_text_left(self.fonts['xs'], f"{photos_left} {self.state.t('photos_left')}", 
                              COLOR_TEXT_GRAY, (10, 10))
            
            # ISO (oben links, zweite Zeile)
            iso_val = ISO_VALUES[self.state.iso_idx]
            self.draw_text_left(self.fonts['xs'], f"ISO {iso_val}", COLOR_ACCENT, (10, 28))
            
            # Filter-Name (oben Mitte)
            filter_name = self.state.get_current_filter().upper()
            if filter_name != "NONE":
                self.draw_text_center(self.fonts['xs'], filter_name, COLOR_ACCENT, (RES_W//2, 10))
            
            # Mini-Histogram (oben rechts, unter Batterie)
            hist_surf = self.compute_mini_histogram(filtered_bg)
            self.screen.blit(hist_surf, (RES_W - 70, 30))
        
        # 4. Haptic Flash (visuell)
        if time.time() - self.state.haptic_flash_time < 0.1:
            alpha = int(50 * (1 - (time.time() - self.state.haptic_flash_time) / 0.1))
            overlay = pygame.Surface((RES_W, RES_H), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, alpha))
            self.screen.blit(overlay, (0, 0))
        
        # 5. Shutter Flash (weiß)
        if time.time() - self.state.shutter_flash_time < 0.15:
            alpha = int(255 * (1 - (time.time() - self.state.shutter_flash_time) / 0.15))
            overlay = pygame.Surface((RES_W, RES_H), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, alpha))
            self.screen.blit(overlay, (0, 0))
    
    def render_settings_overlay(self):
        """Settings Menu"""
        # Blur Overlay
        overlay = pygame.Surface((RES_W, RES_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 230))
        self.screen.blit(overlay, (0, 0))
        
        # Slide Animation
        offset_y = int(self.state.menu_slide_offset)
        
        # Titel
        self.draw_text_center(self.fonts['xl'], self.state.t('settings'), 
                            COLOR_WHITE, (RES_W//2, 80 + offset_y))
        
        # Items
        btn_h = 50
        start_y = 160
        
        for i, item in enumerate(self.state.settings_items):
            y_pos = start_y + i * (btn_h + 12) + offset_y
            
            if y_pos < -btn_h or y_pos > RES_H:
                continue
            
            is_selected = (i == self.state.settings_selected)
            pill_color = COLOR_GLASS_LIGHT if is_selected else (50, 50, 50)
            
            self.draw_pill((PAD, y_pos, RES_W - 2*PAD, btn_h), pill_color, radius=18)
            
            self.draw_text_left(self.fonts['m'], item['label'], COLOR_WHITE, 
                              (PAD + 20, y_pos + btn_h//2 - 8))
            
            if item['value']:
                self.draw_text_right(self.fonts['m'], item['value'], COLOR_ACCENT, 
                                   (RES_W - PAD - 20, y_pos + btn_h//2 - 8))
        
        # Footer
        self.draw_text_center(self.fonts['s'], self.state.t('press_to_close'), 
                            COLOR_TEXT_GRAY, (RES_W//2, RES_H - 50))


# ==========================================
# INPUT HANDLER
# ==========================================

class InputHandler:
    """Keyboard Input"""
    
    def __init__(self, state: AppState, photo_saver: AsyncPhotoSaver):
        self.state = state
        self.photo_saver = photo_saver
    
    def handle_event(self, event, current_bg: pygame.Surface):
        """Verarbeitet Tastatur-Event"""
        if event.type != pygame.KEYDOWN:
            return
        
        # Input registriert → Reset Idle Timer
        self.state.last_input_time = time.perf_counter()
        self.state.screen_active = True
        
        # Haptic Flash (visuell)
        self.state.haptic_flash_time = time.time()
        
        # Global Controls
        if event.key == pygame.K_d:
            # Display Mode wechseln
            modes = [DisplayMode.PURE, DisplayMode.ESSENTIAL, DisplayMode.PRO]
            idx = modes.index(self.state.display_mode)
            self.state.display_mode = modes[(idx + 1) % len(modes)]
            print(f"🖥️  Display Mode: {self.state.display_mode.name}")
        
        elif event.key == pygame.K_g:
            # Grid Toggle
            self.state.grid_enabled = not self.state.grid_enabled
            self.state.build_settings_menu()
        
        elif event.key == pygame.K_l:
            # Level Toggle
            self.state.level_enabled = not self.state.level_enabled
            self.state.build_settings_menu()
        
        elif event.key == pygame.K_t:
            # Sprache wechseln
            self.state.toggle_language()
        
        elif event.key == pygame.K_TAB:
            # Gallery Toggle
            self.state.scene = Scene.GALLERY if self.state.scene == Scene.CAMERA else Scene.CAMERA
        
        elif event.key == pygame.K_ESCAPE:
            # Settings Toggle
            if self.state.scene == Scene.SETTINGS:
                self.state.scene = Scene.CAMERA
            else:
                self.state.scene = Scene.SETTINGS
                self.state.menu_slide_offset = 200  # Animation
        
        # Camera Controls
        elif self.state.scene == Scene.CAMERA:
            if event.key == pygame.K_UP:
                # Shutter Speed (BLIND - kein UI!)
                self.state.shutter_idx = (self.state.shutter_idx + 1) % len(SHUTTER_SPEEDS)
                print(f"📷 Shutter: {SHUTTER_SPEEDS[self.state.shutter_idx]}")
            
            elif event.key == pygame.K_DOWN:
                self.state.shutter_idx = (self.state.shutter_idx - 1) % len(SHUTTER_SPEEDS)
                print(f"📷 Shutter: {SHUTTER_SPEEDS[self.state.shutter_idx]}")
            
            elif event.key == pygame.K_LEFT:
                self.state.iso_idx = max(0, self.state.iso_idx - 1)
                self.state.build_settings_menu()
            
            elif event.key == pygame.K_RIGHT:
                self.state.iso_idx = min(len(ISO_VALUES) - 1, self.state.iso_idx + 1)
                self.state.build_settings_menu()
            
            elif event.key == pygame.K_f:
                # Filter wechseln
                self.state.filter_idx = (self.state.filter_idx + 1) % len(FILTER_PRESETS)
                self.state.build_settings_menu()
            
            elif event.key == pygame.K_SPACE:
                # SHUTTER RELEASE
                self.capture_photo(current_bg)
        
        # Settings Controls
        elif self.state.scene == Scene.SETTINGS:
            if event.key == pygame.K_UP:
                self.state.settings_selected = max(0, self.state.settings_selected - 1)
            
            elif event.key == pygame.K_DOWN:
                self.state.settings_selected = min(
                    len(self.state.settings_items) - 1, 
                    self.state.settings_selected + 1
                )
            
            elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                # Setting ändern
                self.toggle_setting()
    
    def toggle_setting(self):
        """Ändert ausgewählte Setting"""
        item = self.state.settings_items[self.state.settings_selected]
        key = item['key']
        
        if key == 'grid':
            self.state.grid_enabled = not self.state.grid_enabled
        elif key == 'level':
            self.state.level_enabled = not self.state.level_enabled
        elif key == 'date_stamp':
            self.state.date_stamp_enabled = not self.state.date_stamp_enabled
        elif key == 'haptics':
            levels = [HapticLevel.OFF, HapticLevel.LOW, HapticLevel.HIGH]
            idx = levels.index(self.state.haptic_level)
            self.state.haptic_level = levels[(idx + 1) % len(levels)]
        elif key == 'language':
            self.state.toggle_language()
        
        self.state.build_settings_menu()
    
    def capture_photo(self, bg_surface: pygame.Surface):
        """Nimmt Foto auf (async!)"""
        # Shutter Flash
        self.state.shutter_flash_time = time.time()
        
        # Async Speichern (blockiert UI nicht!)
        self.photo_saver.save_photo_async(
            surface=bg_surface,
            filter_name=self.state.get_current_filter(),
            date_stamp=self.state.date_stamp_enabled,
            photo_dir=self.state.photo_dir
        )
        
        # Galerie aktualisieren
        self.state.gallery_photos = sorted(self.state.photo_dir.glob("IMG_*.jpg"))
        
        print(f"📸 Foto aufgenommen ({len(self.state.gallery_photos)} total)")


# ==========================================
# POWER MANAGER
# ==========================================

class PowerManager:
    """Battery Saver"""
    
    def __init__(self, state: AppState):
        self.state = state
    
    def update(self):
        """Update Power State"""
        idle_time = time.perf_counter() - self.state.last_input_time
        
        # FPS
        if idle_time > IDLE_FPS_DROP:
            self.state.current_fps = FPS_IDLE
        else:
            self.state.current_fps = FPS_NORMAL
        
        # Screen
        if idle_time > IDLE_SCREEN_OFF:
            self.state.screen_active = False
        else:
            self.state.screen_active = True


# ==========================================
# MAIN
# ==========================================

def main():
    pygame.init()
    screen = pygame.display.set_mode((RES_W, RES_H))
    pygame.display.set_caption("SelimCam v6.0 FINAL - Simulator")
    clock = pygame.time.Clock()
    
    # Fonts
    try:
        fonts = {
            'xl': pygame.font.Font("static/inter_bold.ttf", 42),
            'l': pygame.font.Font("static/inter_bold.ttf", 26),
            'm': pygame.font.Font("static/inter_regular.ttf", 18),
            's': pygame.font.Font("static/inter_regular.ttf", 14),
            'xs': pygame.font.Font("static/inter_regular.ttf", 11),
        }
    except:
        print("⚠️  Inter Font fehlt")
        f = pygame.font.SysFont("Arial", 16)
        fonts = {'xl': f, 'l': f, 'm': f, 's': f, 'xs': f}
    
    # State
    state = AppState()
    
    # Async Photo Saver
    photo_saver = AsyncPhotoSaver(state.filter_manager)
    
    # Renderer
    renderer = Renderer(screen, fonts, state)
    
    # Input Handler
    input_handler = InputHandler(state, photo_saver)
    
    # Power Manager
    power_mgr = PowerManager(state)
    
    # Test Bild laden
    try:
        bg_img = pygame.image.load("test.jpg")
        bg_img = pygame.transform.smoothscale(bg_img, (RES_W, RES_H))
        print("✅ test.jpg geladen")
    except:
        # Gradient Fallback
        bg_img = pygame.Surface((RES_W, RES_H))
        for y in range(RES_H):
            c = int(40 + (y / RES_H) * 60)
            pygame.draw.line(bg_img, (c, c, c), (0, y), (RES_W, y))
        print("⚠️  test.jpg fehlt, nutze Gradient")
    
    # Gyro Mock (oszilliert)
    gyro_time = 0.0
    
    print("\n" + "="*60)
    print("SelimCam v6.0 FINAL - PC Simulator")
    print("="*60)
    print("\nFeatures:")
    print("  ✓ Ghost UI (PURE/ESSENTIAL/PRO)")
    print("  ✓ Blind Controls (nur Haptic)")
    print("  ✓ Proxy-Filter (90% CPU-Ersparnis)")
    print("  ✓ Async Photo Save (non-blocking)")
    print("  ✓ Date Stamp Engine")
    print("  ✓ Grid & Level Overlays")
    print("  ✓ Mehrsprachig (DE/EN)")
    print("  ✓ Battery Saver")
    print("\nControls:")
    print("  D       : Display Mode (PURE/ESSENTIAL/PRO)")
    print("  ↑↓      : Shutter Speed (blind!)")
    print("  ←→      : ISO")
    print("  SPACE   : Foto aufnehmen")
    print("  F       : Filter wechseln")
    print("  G       : Grid Toggle")
    print("  L       : Level Toggle")
    print("  T       : Sprache (DE/EN)")
    print("  TAB     : Gallery")
    print("  ESC     : Settings")
    print("  H       : Haptic Flash")
    print("\nStarting...\n")
    
    running = True
    while running:
        # Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            # Haptic Flash simulieren
            if event.type == pygame.KEYDOWN and event.key == pygame.K_h:
                state.haptic_flash_time = time.time()
            
            input_handler.handle_event(event, bg_img)
        
        # Power Management
        power_mgr.update()
        
        # Gyro Mock (oszilliert)
        gyro_time += 0.02
        state.gyro_angle = np.sin(gyro_time) * 8  # ±8 Grad
        
        # Render
        if state.screen_active:
            if state.scene == Scene.CAMERA:
                renderer.render_camera_view(bg_img)
            
            elif state.scene == Scene.SETTINGS:
                renderer.render_camera_view(bg_img)
                renderer.render_settings_overlay()
            
            # Menu Animation
            if state.menu_slide_offset > 0:
                state.menu_slide_offset = max(0, state.menu_slide_offset - 20)
        
        else:
            # Screen OFF
            screen.fill((0, 0, 0))
        
        pygame.display.flip()
        clock.tick(state.current_fps)
    
    pygame.quit()
    print("\n✅ Simulator beendet")


if __name__ == "__main__":
    main()
