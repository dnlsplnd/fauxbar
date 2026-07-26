# fauxbar

A foobar2000-styled media player for Linux, built with PySide6 (Qt6).

foobar2000 isn't ported to Linux, so this recreates the parts that matter most:
a dense dark UI, a multi-column sortable playlist, dockable/floatable panels
with persistent layout, and a real-time spectrum analyzer.

## Features

- Playback for mp3/flac/ogg/opus/m4a/wav/wv/ape via Qt Multimedia
- Multi-column playlist (title/artist/album/duration) with tag reading via `mutagen`, click-to-sort, drag-and-drop
- Dockable/floatable panels (Playlist, Now Playing, Spectrum) with layout persisted across restarts
- Spectrum analyzer: Blackman-Harris windowed STFT, log-frequency bar mapping, dB-scaled with attack/release ballistics and peak-hold

## Running

Requires PySide6, mutagen, and numpy:

```
sudo dnf install python3-pyside6 python3-mutagen python3-numpy   # Fedora
python3 main.py
```

## Layout

- `app/player.py` - playback engine wrapping `QMediaPlayer`/`QAudioOutput`, taps decoded PCM via `QAudioBufferOutput` for analysis
- `app/playlist_model.py` - playlist table model and tag reading
- `app/spectrum.py` - spectrum analyzer DSP engine and widget
- `app/main_window.py` - main window, docking, menus, transport controls
