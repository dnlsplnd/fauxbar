from pathlib import Path

import mutagen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from app.playlist_model import format_duration

FIELDS = [
    ("title", "Title"),
    ("artist", "Artist"),
    ("album", "Album"),
    ("tracknumber", "Track Number"),
    ("genre", "Genre"),
    ("date", "Date"),
]


def _read_tags(path: Path) -> dict:
    try:
        audio = mutagen.File(path, easy=True)
    except Exception:
        audio = None
    tags = {}
    if audio is not None and audio.tags is not None:
        for key, _ in FIELDS:
            tags[key] = (audio.tags.get(key) or [""])[0]
    return tags


class TrackPropertiesDialog(QDialog):
    """Views/edits tags for one or more files. Fields left blank on a
    multi-file selection with differing values are left untouched on save -
    only fields the dialog shows non-blank get written, so you can't
    accidentally blank out tags that already differed across files."""

    def __init__(self, paths: list[Path], parent=None):
        super().__init__(parent)
        self.paths = paths
        self.setWindowTitle("Properties")
        self.setMinimumWidth(380)

        all_tags = [_read_tags(p) for p in paths]

        layout = QVBoxLayout(self)

        if len(paths) == 1:
            info_text = str(paths[0])
        else:
            info_text = f"{len(paths)} files selected - fields left blank won't be changed"
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        form = QFormLayout()
        self.edits = {}
        for key, label in FIELDS:
            values = {tags.get(key, "") for tags in all_tags}
            edit = QLineEdit()
            if len(values) == 1:
                edit.setText(next(iter(values)))
            else:
                edit.setPlaceholderText("<multiple values>")
            self.edits[key] = edit
            form.addRow(label, edit)
        layout.addLayout(form)

        if len(paths) == 1:
            duration = 0.0
            try:
                audio = mutagen.File(paths[0])
                if audio is not None and audio.info is not None:
                    duration = getattr(audio.info, "length", 0.0) or 0.0
            except Exception:
                pass
            layout.addWidget(QLabel(f"Duration: {format_duration(duration)}"))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        errors = []
        for path in self.paths:
            try:
                audio = mutagen.File(path, easy=True)
                if audio is None:
                    raise ValueError("unsupported or unrecognised format")
                if audio.tags is None:
                    audio.add_tags()
                for key, edit in self.edits.items():
                    text = edit.text()
                    if text:
                        audio.tags[key] = [text]
                audio.save()
            except Exception as e:
                errors.append(f"{path.name}: {e}")

        if errors:
            QMessageBox.warning(self, "Some files could not be saved", "\n".join(errors))
        self.accept()
