from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import (
    QAudioBufferOutput,
    QAudioDevice,
    QAudioFormat,
    QAudioOutput,
    QMediaDevices,
    QMediaPlayer,
)

OUTPUT_DEVICE_ID_KEY = "playback/output_device_id"

_DTYPE_FOR_SAMPLE_FORMAT = {
    QAudioFormat.SampleFormat.UInt8: np.uint8,
    QAudioFormat.SampleFormat.Int16: np.int16,
    QAudioFormat.SampleFormat.Int32: np.int32,
    QAudioFormat.SampleFormat.Float: np.float32,
}


def _audio_buffer_to_mono_float(buf) -> tuple[np.ndarray, int]:
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
        data = data.reshape(-1, channels).mean(axis=1)
    return data, fmt.sampleRate()


class PlayerEngine(QObject):
    positionChanged = Signal(int)
    durationChanged = Signal(int)
    playingChanged = Signal(bool)
    trackFinished = Signal()
    audioSamples = Signal(object, int)

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
            samples, sample_rate = _audio_buffer_to_mono_float(buf)
        except (KeyError, ValueError):
            return
        self.audioSamples.emit(samples, sample_rate)

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

    def available_output_devices(self) -> list[QAudioDevice]:
        return QMediaDevices.audioOutputs()

    def set_output_device(self, device: QAudioDevice):
        self._output.setDevice(device)

    def restore_output_device(self, settings):
        device_id = settings.value(OUTPUT_DEVICE_ID_KEY)
        if not device_id:
            return
        device_id = bytes(device_id)
        for device in self.available_output_devices():
            if bytes(device.id()) == device_id:
                self.set_output_device(device)
                return

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlayingState

    def position(self) -> int:
        return self._player.position()

    def duration(self) -> int:
        return self._player.duration()
