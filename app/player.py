from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioBufferOutput, QAudioFormat, QAudioOutput, QMediaPlayer

_DTYPE_FOR_SAMPLE_FORMAT = {
    QAudioFormat.SampleFormat.UInt8: np.uint8,
    QAudioFormat.SampleFormat.Int16: np.int16,
    QAudioFormat.SampleFormat.Int32: np.int32,
    QAudioFormat.SampleFormat.Float: np.float32,
}


def _decode_audio_buffer(buf) -> tuple[np.ndarray, int, np.ndarray]:
    """Returns (mono_samples, sample_rate, per_channel_peak) for one buffer."""
    fmt = buf.format()
    dtype = _DTYPE_FOR_SAMPLE_FORMAT[fmt.sampleFormat()]
    raw = np.frombuffer(buf.constData(), dtype=dtype)

    if dtype == np.uint8:
        data = (raw.astype(np.float32) - 128.0) / 128.0
    elif dtype == np.int16:
        data = raw.astype(np.float32) / 32768.0
    elif dtype == np.int32:
        data = raw.astype(np.float32) / 2147483648.0
    else:
        data = raw.astype(np.float32)

    channels = fmt.channelCount()
    if channels > 1:
        by_channel = data.reshape(-1, channels)
        peaks = np.abs(by_channel).max(axis=0)
        mono = by_channel.mean(axis=1)
    else:
        peaks = np.array([np.abs(data).max()], dtype=np.float32) if data.size else np.zeros(1, dtype=np.float32)
        mono = data
    return mono, fmt.sampleRate(), peaks


class PlayerEngine(QObject):
    positionChanged = Signal(int)
    durationChanged = Signal(int)
    playingChanged = Signal(bool)
    trackFinished = Signal()
    audioSamples = Signal(object, int)
    peakLevels = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)

        self._buffer_output = QAudioBufferOutput(self)
        self._player.setAudioBufferOutput(self._buffer_output)
        self._buffer_output.audioBufferReceived.connect(self._on_audio_buffer)

        self._player.positionChanged.connect(lambda p: self.positionChanged.emit(int(p)))
        self._player.durationChanged.connect(lambda d: self.durationChanged.emit(int(d)))
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

    def _on_state_changed(self, state):
        self.playingChanged.emit(state == QMediaPlayer.PlayingState)

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.trackFinished.emit()

    def _on_audio_buffer(self, buf):
        if not buf.isValid():
            return
        try:
            samples, sample_rate, peaks = _decode_audio_buffer(buf)
        except (KeyError, ValueError):
            return
        self.audioSamples.emit(samples, sample_rate)
        self.peakLevels.emit(peaks)

    def load(self, path: Path):
        self._player.setSource(QUrl.fromLocalFile(str(path)))

    def play(self):
        self._player.play()

    def pause(self):
        self._player.pause()

    def stop(self):
        self._player.stop()

    def toggle_play_pause(self):
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self.pause()
        else:
            self.play()

    def set_position(self, ms: int):
        self._player.setPosition(ms)

    def set_volume(self, percent: int):
        self._output.setVolume(max(0.0, min(1.0, percent / 100.0)))

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlayingState

    def position(self) -> int:
        return self._player.position()

    def duration(self) -> int:
        return self._player.duration()
