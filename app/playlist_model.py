from dataclasses import dataclass, field
from pathlib import Path

import mutagen
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".wav", ".wv", ".ape"}

COLUMNS = ["#", "Title", "Artist", "Album", "Duration"]


@dataclass
class Track:
    path: Path
    title: str = ""
    artist: str = ""
    album: str = ""
    track_number: str = ""
    duration: float = 0.0

    def __post_init__(self):
        if not self.title:
            self.title = self.path.stem


def format_duration(seconds: float) -> str:
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def read_track(path: Path) -> Track:
    track = Track(path=path)
    try:
        audio = mutagen.File(path, easy=True)
    except Exception:
        audio = None
    if audio is not None:
        tags = audio.tags or {}
        track.title = (tags.get("title") or [""])[0] or path.stem
        track.artist = (tags.get("artist") or [""])[0]
        track.album = (tags.get("album") or [""])[0]
        track.track_number = (tags.get("tracknumber") or [""])[0]
        if audio.info is not None:
            track.duration = getattr(audio.info, "length", 0.0) or 0.0
    return track


def scan_paths(paths: list[Path]) -> list[Path]:
    files = []
    for p in paths:
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append(child)
        elif p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(p)
    return files


class PlaylistModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks: list[Track] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self.tracks)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return COLUMNS[section]

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.TextAlignmentRole):
            return None
        track = self.tracks[index.row()]
        col = index.column()
        if role == Qt.TextAlignmentRole:
            if col in (0, 4):
                return Qt.AlignRight | Qt.AlignVCenter
            return Qt.AlignLeft | Qt.AlignVCenter
        if col == 0:
            return str(index.row() + 1)
        if col == 1:
            return track.title
        if col == 2:
            return track.artist
        if col == 3:
            return track.album
        if col == 4:
            return format_duration(track.duration)
        return None

    def add_paths(self, paths: list[Path]):
        files = scan_paths(paths)
        if not files:
            return
        start = len(self.tracks)
        self.beginInsertRows(QModelIndex(), start, start + len(files) - 1)
        for f in files:
            self.tracks.append(read_track(f))
        self.endInsertRows()

    def clear(self):
        if not self.tracks:
            return
        self.beginResetModel()
        self.tracks.clear()
        self.endResetModel()

    def sort(self, column: int, order=Qt.AscendingOrder):
        keys = {
            0: lambda t: t.track_number,
            1: lambda t: t.title.lower(),
            2: lambda t: t.artist.lower(),
            3: lambda t: t.album.lower(),
            4: lambda t: t.duration,
        }
        key = keys.get(column)
        if key is None:
            return
        self.layoutAboutToBeChanged.emit()
        self.tracks.sort(key=key, reverse=(order == Qt.DescendingOrder))
        self.layoutChanged.emit()

    def track_at(self, row: int) -> Track | None:
        if 0 <= row < len(self.tracks):
            return self.tracks[row]
        return None

    def total_duration(self) -> float:
        return sum(t.duration for t in self.tracks)
