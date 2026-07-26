# fauxbar

A foobar2000-styled media player for Linux, built with PySide6 (Qt6).

foobar2000 isn't ported to Linux, so this recreates the parts that matter most:
a dense dark UI, a multi-column sortable playlist, dockable/floatable panels
with persistent layout, and a real-time spectrum analyzer.

## Features

- Playback for mp3/flac/ogg/opus/m4a/wav/wv/ape via Qt Multimedia
- Multi-column playlist (title/artist/album/duration) with tag reading via `mutagen`, click-to-sort, drag-and-drop
- Dockable/floatable panels (Playlist, Now Playing, Spectrum, Library, Peak Meter) with layout persisted across restarts
- Spectrum analyzer: Blackman-Harris windowed STFT, log-frequency bar mapping (80 bands, 20Hz-20kHz), Prussian Blue coloring with attack/release ballistics and peak-hold, 60fps
- Library panel: scans configured folders into an Artist/Album/Track tree, with filtering and double-click/context-menu to queue or play
- Peak level meter: per-channel dBFS meter with green/yellow/red zones, peak-hold, and a latching clip indicator

## Running

Requires PySide6, mutagen, and numpy:

```
sudo dnf install python3-pyside6 python3-mutagen python3-numpy   # Fedora
python3 main.py
```

Or grab the latest `.AppImage` from [Releases](https://github.com/dnlsplnd/fauxbar/releases) - no dependencies needed, just `chmod +x` and run.

## Building the AppImage

```
./scripts/build-appimage.sh
```

Produces `fauxbar-x86_64.AppImage`. Uses a dedicated venv with a plain PyPI
numpy wheel rather than the system one - Fedora's `python3-numpy` links
against FlexiBLAS, which resolves its actual BLAS backend via a runtime
dlopen that PyInstaller can't trace, so the bundled app would abort on
startup. A PyPI wheel bundles its BLAS statically instead.

## Layout

- `app/player.py` - playback engine wrapping `QMediaPlayer`/`QAudioOutput`, taps decoded PCM via `QAudioBufferOutput` for analysis
- `app/playlist_model.py` - playlist table model and tag reading
- `app/spectrum.py` - spectrum analyzer DSP engine and widget
- `app/library.py` - library folder scanning and browser tree
- `app/peak_meter.py` - per-channel peak level meter with clip detection
- `app/main_window.py` - main window, docking, menus, transport controls
- `scripts/build-appimage.sh` - builds the portable `.AppImage`
