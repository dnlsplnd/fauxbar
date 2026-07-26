import math
import time

import numpy as np
from PySide6.QtCore import QRectF, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

FFT_SIZE = 4096
HOP_SIZE = FFT_SIZE // 4
NUM_BARS = 40
FREQ_MIN = 20.0
FREQ_MAX = 20000.0
DB_FLOOR = -90.0

PRUSSIAN_BLUE = QColor("#003153")

ATTACK_TAU = 0.008
RELEASE_TAU = 0.20
PEAK_HOLD_TIME = 0.8
PEAK_RELEASE_TAU = 0.6


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
        fft_size: int = FFT_SIZE,
        hop_size: int = HOP_SIZE,
        num_bars: int = NUM_BARS,
        freq_min: float = FREQ_MIN,
        freq_max: float = FREQ_MAX,
    ):
        self.fft_size = fft_size
        self.hop_size = hop_size
        self.num_bars = num_bars
        self.freq_min = freq_min
        self.freq_max = freq_max

        self._window = _blackman_harris(fft_size)
        # Coherent-gain correction: recovers true amplitude of a windowed sinusoid
        # rather than the attenuated raw FFT magnitude.
        self._window_gain = self._window.sum() / 2.0

        self._buffer = np.zeros(0, dtype=np.float32)
        self._sample_rate = None
        self._bar_plan = None
        self._latest_db = np.full(num_bars, DB_FLOOR, dtype=np.float32)

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
        self._latest_db = np.clip(bars, DB_FLOOR, 0.0)

    def latest(self) -> np.ndarray:
        return self._latest_db

    @property
    def sample_rate(self):
        return self._sample_rate


class SpectrumWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = SpectrumEngine()
        self._display = np.full(self.engine.num_bars, DB_FLOOR, dtype=np.float32)
        self._peak = np.full(self.engine.num_bars, DB_FLOOR, dtype=np.float32)
        self._peak_hold = np.zeros(self.engine.num_bars, dtype=np.float32)
        self._active = False
        self._last_tick = None

        self.setMinimumHeight(90)

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def on_audio_samples(self, samples, sample_rate):
        self.engine.ingest(samples, sample_rate)
        self._active = True

    def set_active(self, active: bool):
        self._active = active

    def _tick(self):
        now = time.monotonic()
        dt = max(now - self._last_tick, 1e-3) if self._last_tick is not None else 1 / 30
        self._last_tick = now

        targets = self.engine.latest() if self._active else np.full_like(self._display, DB_FLOOR)

        attack_coeff = math.exp(-dt / ATTACK_TAU)
        release_coeff = math.exp(-dt / RELEASE_TAU)
        rising = targets > self._display
        coeff = np.where(rising, attack_coeff, release_coeff)
        self._display = targets * (1 - coeff) + self._display * coeff

        new_peak = self._display >= self._peak
        self._peak_hold = np.where(new_peak, 0.0, self._peak_hold + dt)
        peak_release_coeff = math.exp(-dt / PEAK_RELEASE_TAU)
        held = self._peak_hold <= PEAK_HOLD_TIME
        self._peak = np.where(
            new_peak,
            self._display,
            np.where(held, self._peak, np.maximum(self._display, self._peak * peak_release_coeff)),
        )

        self.update()

    def _color_for_frac(self, frac: float) -> QColor:
        # Fixed Prussian Blue hue/saturation; brightness scales with level so
        # the loudest bars land on the exact named color and quieter ones
        # fade toward black, rather than sweeping through other hues.
        hue, sat, value, _ = PRUSSIAN_BLUE.getHsvF()
        return QColor.fromHsvF(hue, sat, value * (0.08 + 0.92 * frac))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#181818"))

        w = self.width()
        h = self.height()
        n = self.engine.num_bars
        bar_w = w / n
        span = -DB_FLOOR

        for i in range(n):
            frac = max(0.0, min(1.0, (self._display[i] - DB_FLOOR) / span))
            bar_h = frac * h
            x = i * bar_w
            painter.fillRect(QRectF(x, h - bar_h, max(bar_w - 1, 1), bar_h), self._color_for_frac(frac))

            peak_frac = max(0.0, min(1.0, (self._peak[i] - DB_FLOOR) / span))
            peak_y = h - peak_frac * h
            painter.fillRect(QRectF(x, peak_y - 1.5, max(bar_w - 1, 1), 1.5), QColor("#e8e8e8"))

        painter.setPen(QColor("#555555"))
        for label_freq in (100, 1000, 10000):
            if label_freq <= 0:
                continue
            log_min = math.log10(self.engine.freq_min)
            log_max = math.log10(min(self.engine.freq_max, (self.engine.sample_rate or 44100) / 2))
            if log_max <= log_min:
                continue
            frac_x = (math.log10(label_freq) - log_min) / (log_max - log_min)
            if not 0.0 <= frac_x <= 1.0:
                continue
            x = frac_x * w
            painter.drawLine(int(x), 0, int(x), h)
            label = f"{label_freq // 1000}k" if label_freq >= 1000 else str(label_freq)
            painter.drawText(int(x) + 2, h - 4, label)
