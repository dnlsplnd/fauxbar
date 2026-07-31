import math
import time

import numpy as np
from PySide6.QtCore import QRectF, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

FREQ_MIN = 20.0
FREQ_MAX = 20000.0

AXIS_LABEL_FREQS = (20, 100, 1000, 10000, 20000)
AXIS_HEIGHT = 16

PEAK_RELEASE_TAU = 0.6

# Settings keys and defaults - read by SpectrumWidget, written by the
# Preferences dialog's Display > Spectrum and Advanced pages.
SETTINGS_COLOR = "spectrum/color"
SETTINGS_BRIGHTNESS_PERCENT = "spectrum/brightness_percent"
SETTINGS_BARS = "spectrum/bars"
SETTINGS_FFT_SIZE = "spectrum/fft_size"
SETTINGS_DB_FLOOR = "spectrum/db_floor"
SETTINGS_ATTACK_MS = "spectrum/attack_ms"
SETTINGS_RELEASE_MS = "spectrum/release_ms"
SETTINGS_PEAK_HOLD_MS = "spectrum/peak_hold_ms"

DEFAULT_COLOR = "#003153"  # Prussian Blue
DEFAULT_BRIGHTNESS_PERCENT = 135
DEFAULT_BARS = 80
DEFAULT_FFT_SIZE = 4096
DEFAULT_DB_FLOOR = -90.0
DEFAULT_ATTACK_MS = 8
DEFAULT_RELEASE_MS = 200
DEFAULT_PEAK_HOLD_MS = 800

FFT_SIZE_CHOICES = (2048, 4096, 8192, 16384)


def _blackman_harris(n: int) -> np.ndarray:
    # 4-term Blackman-Harris: ~-92 dB sidelobes, far tighter leakage suppression
    # than a plain Hann window, at the cost of a wider main lobe.
    a0, a1, a2, a3 = 0.35875, 0.48829, 0.14128, 0.01168
    i = np.arange(n)
    return (
        a0
        - a1 * np.cos(2 * np.pi * i / (n - 1))
        + a2 * np.cos(4 * np.pi * i / (n - 1))
        - a3 * np.cos(6 * np.pi * i / (n - 1))
    ).astype(np.float32)


class SpectrumEngine:
    """Turns a stream of mono PCM samples into log-frequency dB bars via STFT."""

    def __init__(
        self,
        fft_size: int = DEFAULT_FFT_SIZE,
        hop_size: int | None = None,
        num_bars: int = DEFAULT_BARS,
        freq_min: float = FREQ_MIN,
        freq_max: float = FREQ_MAX,
        db_floor: float = DEFAULT_DB_FLOOR,
    ):
        self.fft_size = fft_size
        self.hop_size = hop_size or fft_size // 4
        self.num_bars = num_bars
        self.freq_min = freq_min
        self.freq_max = freq_max
        self.db_floor = db_floor

        self._window = _blackman_harris(fft_size)
        # Coherent-gain correction: recovers true amplitude of a windowed sinusoid
        # rather than the attenuated raw FFT magnitude.
        self._window_gain = self._window.sum() / 2.0

        self._buffer = np.zeros(0, dtype=np.float32)
        self._sample_rate = None
        self._bar_plan = None
        self._latest_db = np.full(num_bars, db_floor, dtype=np.float32)

    def _ensure_bar_plan(self, sample_rate: int):
        if self._sample_rate == sample_rate and self._bar_plan is not None:
            return
        self._sample_rate = sample_rate
        nyquist = sample_rate / 2.0
        f_max = min(self.freq_max, nyquist * 0.999)
        edges = np.logspace(math.log10(self.freq_min), math.log10(f_max), self.num_bars + 1)
        bin_resolution = sample_rate / self.fft_size
        n_bins = self.fft_size // 2 + 1

        plan = []
        for i in range(self.num_bars):
            f_lo, f_hi = edges[i], edges[i + 1]
            if (f_hi - f_lo) < bin_resolution:
                # Bar is narrower than one FFT bin (typical at the bass end of a
                # log scale) - interpolate between the two nearest bins instead
                # of snapping to one, so adjacent bars don't read identical bins.
                f_center = math.sqrt(f_lo * f_hi)
                plan.append(("interp", f_center / bin_resolution))
            else:
                # Bar spans multiple bins (typical at the treble end) - take the
                # loudest bin in range so narrow peaks aren't averaged away.
                lo = max(0, int(math.floor(f_lo / bin_resolution)))
                hi = min(n_bins - 1, int(math.ceil(f_hi / bin_resolution)))
                plan.append(("range", lo, max(hi, lo)))
        self._bar_plan = plan

    def ingest(self, samples: np.ndarray, sample_rate: int):
        self._ensure_bar_plan(sample_rate)
        if self._buffer.size:
            self._buffer = np.concatenate([self._buffer, samples])
        else:
            self._buffer = samples.astype(np.float32, copy=True)

        while self._buffer.size >= self.fft_size:
            self._process_frame(self._buffer[: self.fft_size])
            self._buffer = self._buffer[self.hop_size :]

    def _process_frame(self, frame: np.ndarray):
        spectrum = np.fft.rfft(frame * self._window)
        magnitude = np.abs(spectrum) / self._window_gain
        db = 20.0 * np.log10(np.maximum(magnitude, 1e-9))

        bars = np.empty(self.num_bars, dtype=np.float32)
        for i, entry in enumerate(self._bar_plan):
            if entry[0] == "interp":
                bin_pos = entry[1]
                lo = min(int(math.floor(bin_pos)), len(db) - 1)
                hi = min(lo + 1, len(db) - 1)
                frac = bin_pos - lo
                bars[i] = db[lo] * (1 - frac) + db[hi] * frac
            else:
                _, lo, hi = entry
                bars[i] = np.max(db[lo : hi + 1])
        self._latest_db = np.clip(bars, self.db_floor, 0.0)

    def latest(self) -> np.ndarray:
        return self._latest_db

    @property
    def sample_rate(self):
        return self._sample_rate


class SpectrumWidget(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._active = False
        self._last_tick = None

        self._load_config()

        self.setMinimumHeight(90 + AXIS_HEIGHT)

        self._timer = QTimer(self)
        self._timer.setInterval(round(1000 / 60))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _load_config(self):
        s = self.settings
        self.color = QColor(s.value(SETTINGS_COLOR, DEFAULT_COLOR, type=str))
        brightness_percent = s.value(SETTINGS_BRIGHTNESS_PERCENT, DEFAULT_BRIGHTNESS_PERCENT, type=int)
        self.brightness_boost = brightness_percent / 100.0
        num_bars = s.value(SETTINGS_BARS, DEFAULT_BARS, type=int)
        fft_size = s.value(SETTINGS_FFT_SIZE, DEFAULT_FFT_SIZE, type=int)
        db_floor = s.value(SETTINGS_DB_FLOOR, DEFAULT_DB_FLOOR, type=float)
        self.attack_tau = max(s.value(SETTINGS_ATTACK_MS, DEFAULT_ATTACK_MS, type=int), 1) / 1000.0
        self.release_tau = max(s.value(SETTINGS_RELEASE_MS, DEFAULT_RELEASE_MS, type=int), 1) / 1000.0
        self.peak_hold_s = s.value(SETTINGS_PEAK_HOLD_MS, DEFAULT_PEAK_HOLD_MS, type=int) / 1000.0

        self.engine = SpectrumEngine(
            fft_size=fft_size,
            hop_size=fft_size // 4,
            num_bars=num_bars,
            freq_min=FREQ_MIN,
            freq_max=FREQ_MAX,
            db_floor=db_floor,
        )
        self._display = np.full(num_bars, db_floor, dtype=np.float32)
        self._peak = np.full(num_bars, db_floor, dtype=np.float32)
        self._peak_hold = np.zeros(num_bars, dtype=np.float32)

    def apply_settings(self):
        """Reloads DSP/appearance config from settings. Called by the
        Preferences dialog on Apply/OK; resets the bar smoothing state
        since the bar count or FFT size may have changed."""
        self._load_config()
        self.update()

    def on_audio_samples(self, samples, sample_rate):
        self.engine.ingest(samples, sample_rate)
        self._active = True

    def set_active(self, active: bool):
        self._active = active

    def _tick(self):
        now = time.monotonic()
        dt = max(now - self._last_tick, 1e-3) if self._last_tick is not None else 1 / 30
        self._last_tick = now

        db_floor = self.engine.db_floor
        targets = self.engine.latest() if self._active else np.full_like(self._display, db_floor)

        attack_coeff = math.exp(-dt / self.attack_tau)
        release_coeff = math.exp(-dt / self.release_tau)
        rising = targets > self._display
        coeff = np.where(rising, attack_coeff, release_coeff)
        self._display = targets * (1 - coeff) + self._display * coeff

        new_peak = self._display >= self._peak
        self._peak_hold = np.where(new_peak, 0.0, self._peak_hold + dt)
        peak_release_coeff = math.exp(-dt / PEAK_RELEASE_TAU)
        held = self._peak_hold <= self.peak_hold_s
        # Decay toward db_floor (not toward 0 dB): blend the dB value itself
        # toward the floor, rather than scaling it - scaling a negative dB
        # number by a sub-1 factor moves it *up* toward 0, not down.
        decayed = db_floor + (self._peak - db_floor) * peak_release_coeff
        self._peak = np.where(
            new_peak,
            self._display,
            np.where(held, self._peak, np.maximum(self._display, decayed)),
        )

        self.update()

    def _color_for_frac(self, frac: float) -> QColor:
        # Fixed hue/saturation from the configured color; brightness scales
        # with level so the loudest bars land near the named color (boosted
        # a bit by default, since Prussian Blue itself is quite dark) and
        # quieter ones fade toward black, rather than sweeping through hues.
        hue, sat, value, _ = self.color.getHsvF()
        value = min(1.0, value * self.brightness_boost)
        return QColor.fromHsvF(hue, sat, value * (0.08 + 0.92 * frac))

    @staticmethod
    def _format_freq(freq_hz: float) -> str:
        if freq_hz >= 1000:
            khz = freq_hz / 1000
            return f"{khz:g} kHz"
        return f"{freq_hz:g} Hz"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#181818"))

        w = self.width()
        h = self.height() - AXIS_HEIGHT
        n = self.engine.num_bars
        bar_w = w / n
        span = -self.engine.db_floor

        for i in range(n):
            frac = max(0.0, min(1.0, (self._display[i] - self.engine.db_floor) / span))
            bar_h = frac * h
            x = i * bar_w
            painter.fillRect(QRectF(x, h - bar_h, max(bar_w - 1, 1), bar_h), self._color_for_frac(frac))

            peak_frac = max(0.0, min(1.0, (self._peak[i] - self.engine.db_floor) / span))
            peak_y = h - peak_frac * h
            painter.fillRect(QRectF(x, peak_y - 1.5, max(bar_w - 1, 1), 1.5), QColor("#e8e8e8"))

        log_min = math.log10(self.engine.freq_min)
        log_max = math.log10(min(self.engine.freq_max, (self.engine.sample_rate or 44100) / 2))
        if log_max <= log_min:
            return

        metrics = painter.fontMetrics()
        text_y = h + metrics.ascent() + (AXIS_HEIGHT - metrics.height()) // 2

        for label_freq in AXIS_LABEL_FREQS:
            frac_x = (math.log10(label_freq) - log_min) / (log_max - log_min)
            if not 0.0 <= frac_x <= 1.0:
                continue
            x = frac_x * w

            painter.setPen(QColor("#555555"))
            painter.drawLine(int(x), 0, int(x), h)

            label = self._format_freq(label_freq)
            label_w = metrics.horizontalAdvance(label)
            if frac_x <= 0.02:
                text_x = x
            elif frac_x >= 0.98:
                text_x = x - label_w
            else:
                text_x = x - label_w / 2

            painter.setPen(QColor("#888888"))
            painter.drawText(int(text_x), text_y, label)
