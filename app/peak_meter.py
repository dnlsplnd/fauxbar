import math
import time

import numpy as np
from PySide6.QtCore import QRectF, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

DB_FLOOR = -60.0
CLIP_THRESHOLD_DB = -0.3
CLIP_HOLD_TIME = 2.0

ATTACK_TAU = 0.001
RELEASE_TAU = 0.30
PEAK_HOLD_TIME = 1.5
PEAK_RELEASE_TAU = 0.8

GREEN_ZONE_DB = -18.0
YELLOW_ZONE_DB = -6.0

GREEN = QColor("#3fae4a")
YELLOW = QColor("#d9b93a")
RED = QColor("#c0392b")


def _linear_to_db(x: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(x, 1e-6))


class PeakMeterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._channels = 2
        self._targets = np.full(self._channels, DB_FLOOR, dtype=np.float32)
        self._display = np.full(self._channels, DB_FLOOR, dtype=np.float32)
        self._peak_hold = np.full(self._channels, DB_FLOOR, dtype=np.float32)
        self._peak_hold_timer = np.zeros(self._channels, dtype=np.float32)
        self._clip_timer = np.zeros(self._channels, dtype=np.float32)
        self._active = False
        self._last_tick = None

        self.setMinimumWidth(50)

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def on_peak_levels(self, peaks):
        peaks = np.asarray(peaks, dtype=np.float32)
        if peaks.size != self._channels:
            self._channels = peaks.size
            self._targets = np.full(self._channels, DB_FLOOR, dtype=np.float32)
            self._display = np.full(self._channels, DB_FLOOR, dtype=np.float32)
            self._peak_hold = np.full(self._channels, DB_FLOOR, dtype=np.float32)
            self._peak_hold_timer = np.zeros(self._channels, dtype=np.float32)
            self._clip_timer = np.zeros(self._channels, dtype=np.float32)

        db = _linear_to_db(peaks)
        # Buffers can arrive faster than the repaint tick - keep the loudest
        # since the last tick consumed it, so short transients aren't missed.
        self._targets = np.maximum(self._targets, db)
        self._clip_timer = np.where(db >= CLIP_THRESHOLD_DB, CLIP_HOLD_TIME, self._clip_timer)
        self._active = True

    def set_active(self, active: bool):
        self._active = active

    def _tick(self):
        now = time.monotonic()
        dt = max(now - self._last_tick, 1e-3) if self._last_tick is not None else 1 / 30
        self._last_tick = now

        targets = self._targets if self._active else np.full_like(self._display, DB_FLOOR)

        attack_coeff = math.exp(-dt / ATTACK_TAU)
        release_coeff = math.exp(-dt / RELEASE_TAU)
        rising = targets > self._display
        coeff = np.where(rising, attack_coeff, release_coeff)
        self._display = targets * (1 - coeff) + self._display * coeff
        # Consumed - next tick's target should reflect only new buffers, not
        # this same peak lingering forever.
        self._targets = self._display.copy()

        new_peak = self._display >= self._peak_hold
        self._peak_hold_timer = np.where(new_peak, 0.0, self._peak_hold_timer + dt)
        peak_release_coeff = math.exp(-dt / PEAK_RELEASE_TAU)
        held = self._peak_hold_timer <= PEAK_HOLD_TIME
        # Decay toward the floor (not toward 0 dB): blend the dB value itself
        # toward DB_FLOOR, rather than scaling it, since scaling a negative
        # dB number by a sub-1 factor moves it *up* toward 0, not down.
        decayed = DB_FLOOR + (self._peak_hold - DB_FLOOR) * peak_release_coeff
        self._peak_hold = np.where(
            new_peak, self._display, np.where(held, self._peak_hold, np.maximum(self._display, decayed))
        )

        self._clip_timer = np.maximum(0.0, self._clip_timer - dt)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#181818"))

        w = self.width()
        h = self.height()
        n = max(self._channels, 1)
        clip_h = 6
        meter_top = clip_h + 2
        meter_bottom = h
        meter_h = meter_bottom - meter_top
        span = -DB_FLOOR

        gap = 3
        bar_w = (w - gap * (n + 1)) / n

        green_top_frac = max(0.0, min(1.0, (GREEN_ZONE_DB - DB_FLOOR) / span))
        yellow_top_frac = max(0.0, min(1.0, (YELLOW_ZONE_DB - DB_FLOOR) / span))
        zones = ((0.0, green_top_frac, GREEN), (green_top_frac, yellow_top_frac, YELLOW), (yellow_top_frac, 1.0, RED))

        def frac_to_y(frac):
            return meter_bottom - frac * meter_h

        for ch in range(n):
            x = gap + ch * (bar_w + gap)
            bar_frac = max(0.0, min(1.0, (self._display[ch] - DB_FLOOR) / span))

            for start_frac, end_frac, color in zones:
                filled_end = min(end_frac, bar_frac)
                if filled_end <= start_frac:
                    continue
                y_top = frac_to_y(filled_end)
                y_bottom = frac_to_y(start_frac)
                painter.fillRect(QRectF(x, y_top, bar_w, y_bottom - y_top), color)

            peak_frac = max(0.0, min(1.0, (self._peak_hold[ch] - DB_FLOOR) / span))
            peak_y = frac_to_y(peak_frac)
            painter.fillRect(QRectF(x, peak_y - 1, bar_w, 2), QColor("#e8e8e8"))

            clipping = self._clip_timer[ch] > 0
            clip_color = QColor("#ff2b2b") if clipping else QColor("#3a1a1a")
            painter.fillRect(QRectF(x, 0, bar_w, clip_h), clip_color)
