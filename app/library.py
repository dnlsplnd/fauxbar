from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.playlist_model import read_track, scan_paths

FOLDERS_KEY = "library/folders"


def _track_number_key(track):
    raw = (track.track_number or "").split("/")[0].strip()
    try:
        return (0, int(raw))
    except ValueError:
        return (1, track.title.lower())


class LibraryPanel(QWidget):
    addTracksRequested = Signal(list)
    playTracksRequested = Signal(list)
    propertiesRequested = Signal(list)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._folders = self._load_folders()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        toolbar_row = QHBoxLayout()
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Filter library...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.add_folder_btn = QPushButton("Add Folder...", self)
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.rescan_btn = QPushButton("Rescan", self)
        self.rescan_btn.clicked.connect(self._rebuild_tree)
        toolbar_row.addWidget(self.filter_edit, stretch=1)
        toolbar_row.addWidget(self.add_folder_btn)
        toolbar_row.addWidget(self.rescan_btn)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        layout.addLayout(toolbar_row)
        layout.addWidget(self.tree)

        if self._folders:
            self._rebuild_tree()

    # ---- persistence ----

    def _load_folders(self) -> list[str]:
        folders = self.settings.value(FOLDERS_KEY, [])
        if isinstance(folders, str):
            return [folders] if folders else []
        return list(folders or [])

    def _save_folders(self):
        self.settings.setValue(FOLDERS_KEY, self._folders)

    # ---- folder management ----

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Add Library Folder")
        if folder and folder not in self._folders:
            self._folders.append(folder)
            self._save_folders()
            self._rebuild_tree()

    def refresh(self):
        self._rebuild_tree()

    def folders(self) -> list[str]:
        return list(self._folders)

    def set_folders(self, folders: list[str]):
        self._folders = list(folders)
        self._save_folders()
        self._rebuild_tree()

    # ---- scanning / tree building ----

    def _rebuild_tree(self):
        self.tree.clear()
        if not self._folders:
            return

        files = scan_paths([Path(f) for f in self._folders])
        grouped = defaultdict(lambda: defaultdict(list))
        for f in files:
            track = read_track(f)
            artist = track.artist or "Unknown Artist"
            album = track.album or "Unknown Album"
            grouped[artist][album].append(track)

        for artist in sorted(grouped.keys(), key=str.lower):
            artist_item = QTreeWidgetItem([artist])
            for album in sorted(grouped[artist].keys(), key=str.lower):
                album_item = QTreeWidgetItem([album])
                for track in sorted(grouped[artist][album], key=_track_number_key):
                    prefix = f"{track.track_number.split('/')[0]}. " if track.track_number else ""
                    track_item = QTreeWidgetItem([f"{prefix}{track.title}"])
                    track_item.setData(0, Qt.UserRole, track.path)
                    album_item.addChild(track_item)
                artist_item.addChild(album_item)
            self.tree.addTopLevelItem(artist_item)

        self._apply_filter(self.filter_edit.text())

    # ---- selection / activation ----

    def _collect_paths(self, item: QTreeWidgetItem) -> list[Path]:
        path = item.data(0, Qt.UserRole)
        if path is not None:
            return [path]
        paths = []
        for i in range(item.childCount()):
            paths.extend(self._collect_paths(item.child(i)))
        return paths

    def _on_item_double_clicked(self, item, column):
        paths = self._collect_paths(item)
        if paths:
            self.playTracksRequested.emit(paths)

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        add_action = menu.addAction("Add to Playlist")
        play_action = menu.addAction("Add && Play")
        menu.addSeparator()
        properties_action = menu.addAction("Properties...")
        chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        paths = self._collect_paths(item)
        if not paths:
            return
        if chosen is add_action:
            self.addTracksRequested.emit(paths)
        elif chosen is play_action:
            self.playTracksRequested.emit(paths)
        elif chosen is properties_action:
            self.propertiesRequested.emit(paths)

    # ---- filtering ----

    def _apply_filter(self, text: str):
        text = text.lower().strip()
        for i in range(self.tree.topLevelItemCount()):
            self._filter_item(self.tree.topLevelItem(i), text)

    def _filter_item(self, item: QTreeWidgetItem, text: str) -> bool:
        if not text:
            item.setHidden(False)
            for i in range(item.childCount()):
                self._filter_item(item.child(i), text)
            return True

        self_match = text in item.text(0).lower()
        child_match = False
        for i in range(item.childCount()):
            if self._filter_item(item.child(i), text):
                child_match = True
        visible = self_match or child_match
        item.setHidden(not visible)
        if visible and child_match:
            item.setExpanded(True)
        return visible
