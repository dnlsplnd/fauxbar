import base64
from pathlib import Path

import mutagen
from mutagen.flac import Picture
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


def extract_cover_art(path: Path) -> bytes | None:
    try:
        audio = mutagen.File(path)
    except Exception:
        return None
    if audio is None:
        return None

    # FLAC exposes pictures directly on the file object.
    pictures = getattr(audio, "pictures", None)
    if pictures:
        return pictures[0].data

    tags = getattr(audio, "tags", None)
    if tags is None:
        return None

    # ID3 (MP3, WAV-with-ID3): APIC frames.
    try:
        apics = tags.getall("APIC")
        if apics:
            return apics[0].data
    except AttributeError:
        pass

    # MP4/M4A: 'covr' atom.
    if "covr" in tags:
        covers = tags["covr"]
        if covers:
            return bytes(covers[0])

    # Vorbis comments (OGG/Opus): base64-encoded FLAC Picture block.
    for key in ("METADATA_BLOCK_PICTURE", "metadata_block_picture"):
        if key in tags and tags[key]:
            try:
                return Picture(base64.b64decode(tags[key][0])).data
            except Exception:
                pass

    return None


class CoverArtWidget(QWidget):
    """Always renders as a centered square, regardless of the dock's actual
    aspect ratio - crops to fill rather than letterboxing, like most media
    players' album art display."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self.setMinimumSize(80, 80)

    def set_track(self, path):
        pixmap = None
        if path is not None:
            data = extract_cover_art(path)
            if data:
                candidate = QPixmap()
                if candidate.loadFromData(data):
                    pixmap = candidate
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1c1c1c"))

        side = min(self.width(), self.height())
        x = (self.width() - side) / 2
        y = (self.height() - side) / 2
        square = QRectF(x, y, side, side)

        if self._pixmap is not None and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                int(side), int(side), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            src_x = (scaled.width() - side) / 2
            src_y = (scaled.height() - side) / 2
            painter.drawPixmap(square, scaled, QRectF(src_x, src_y, side, side))
        else:
            painter.setPen(QColor("#555555"))
            painter.drawText(square, Qt.AlignCenter, "No Cover")
