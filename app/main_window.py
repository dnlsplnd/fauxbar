from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.library import LibraryPanel
from app.playlist_model import PlaylistModel, format_duration
from app.player import PlayerEngine
from app.spectrum import SpectrumWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("fauxbar")
        self.resize(900, 560)
        self.setAcceptDrops(True)

        self.model = PlaylistModel(self)
        self.player = PlayerEngine(self)
        self.current_row = -1
        self._user_seeking = False
        self.settings = QSettings("fauxbar", "fauxbar")

        self._build_ui()
        self._build_menu()
        self._wire_signals()
        self._update_status_bar()

    # ---- UI construction ----

    def _build_ui(self):
        self.setDockNestingEnabled(True)
        # Give the left dock area the full window height (both corners) rather
        # than the Qt default, which lets Top-area content claim the top-left
        # corner and squeezes any Left dock into a sliver at the bottom.
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)

        self.table = QTableView(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(20)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(4, 70)
        self.table.doubleClicked.connect(self._on_row_double_clicked)

        self.playlist_dock = QDockWidget("Playlist", self)
        self.playlist_dock.setObjectName("PlaylistDock")
        self.playlist_dock.setWidget(self.table)

        self.np_title_label = QLabel("Nothing playing")
        self.np_title_label.setObjectName("NowPlayingTitle")
        self.np_album_label = QLabel("")
        self.np_album_label.setObjectName("NowPlayingAlbum")
        now_playing_widget = QWidget(self)
        np_layout = QVBoxLayout(now_playing_widget)
        np_layout.addWidget(self.np_title_label)
        np_layout.addWidget(self.np_album_label)
        np_layout.addStretch()

        self.now_playing_dock = QDockWidget("Now Playing", self)
        self.now_playing_dock.setObjectName("NowPlayingDock")
        self.now_playing_dock.setWidget(now_playing_widget)

        self.spectrum_widget = SpectrumWidget(self)
        self.spectrum_dock = QDockWidget("Spectrum", self)
        self.spectrum_dock.setObjectName("SpectrumDock")
        self.spectrum_dock.setWidget(self.spectrum_widget)

        self.addDockWidget(Qt.TopDockWidgetArea, self.now_playing_dock)
        self.splitDockWidget(self.now_playing_dock, self.spectrum_dock, Qt.Vertical)
        self.splitDockWidget(self.spectrum_dock, self.playlist_dock, Qt.Vertical)

        self.library_widget = LibraryPanel(self.settings, self)
        self.library_dock = QDockWidget("Library", self)
        self.library_dock.setObjectName("LibraryDock")
        self.library_dock.setWidget(self.library_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.library_dock)

        # resizeDocks needs real window geometry to establish proportions
        # correctly - calling it during construction (before the window is
        # shown) causes the requested sizes to be ignored. Defer it, and
        # capture the "factory default" layout/restore any saved one only
        # after that, so Reset Layout snaps back to the corrected sizes.
        QTimer.singleShot(0, self._finish_layout_setup)

        self.transport = QWidget(self)
        self.transport.setObjectName("TransportBar")
        transport_layout = QHBoxLayout(self.transport)
        transport_layout.setContentsMargins(8, 6, 8, 6)

        self.btn_prev = QPushButton("|<")
        self.btn_play = QPushButton("Play")
        self.btn_stop = QPushButton("Stop")
        self.btn_next = QPushButton(">|")
        for b in (self.btn_prev, self.btn_play, self.btn_stop, self.btn_next):
            transport_layout.addWidget(b)

        self.elapsed_label = QLabel("0:00")
        self.elapsed_label.setObjectName("TimeLabel")
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.total_label = QLabel("0:00")
        self.total_label.setObjectName("TimeLabel")

        transport_layout.addWidget(self.elapsed_label)
        transport_layout.addWidget(self.seek_slider, stretch=1)
        transport_layout.addWidget(self.total_label)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(100)
        transport_layout.addWidget(QLabel("Vol"))
        transport_layout.addWidget(self.volume_slider)

        self.transport_toolbar = QToolBar("Transport", self)
        self.transport_toolbar.setObjectName("TransportToolBar")
        self.transport_toolbar.setMovable(True)
        self.transport_toolbar.addWidget(self.transport)
        self.addToolBar(Qt.BottomToolBarArea, self.transport_toolbar)

        self.player.set_volume(self.volume_slider.value())

    def _finish_layout_setup(self):
        self.resizeDocks([self.now_playing_dock, self.spectrum_dock], [60, 150], Qt.Vertical)
        self.resizeDocks(
            [self.library_dock, self.now_playing_dock], [220, max(self.width() - 220, 400)], Qt.Horizontal
        )
        self._default_geometry = self.saveGeometry()
        self._default_state = self.saveState()
        self._restore_layout()

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("&File")

        add_files_action = QAction("Add Files...", self)
        add_files_action.setShortcut(QKeySequence.Open)
        add_files_action.triggered.connect(self._add_files_dialog)
        file_menu.addAction(add_files_action)

        add_folder_action = QAction("Add Folder...", self)
        add_folder_action.triggered.connect(self._add_folder_dialog)
        file_menu.addAction(add_folder_action)

        file_menu.addSeparator()

        clear_action = QAction("Clear Playlist", self)
        clear_action.triggered.connect(self._clear_playlist)
        file_menu.addAction(clear_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        playback_menu = self.menuBar().addMenu("&Playback")

        play_pause_action = QAction("Play/Pause", self)
        play_pause_action.setShortcut(Qt.Key_Space)
        play_pause_action.triggered.connect(self._on_play_pause_clicked)
        playback_menu.addAction(play_pause_action)

        next_action = QAction("Next", self)
        next_action.triggered.connect(self._play_next)
        playback_menu.addAction(next_action)

        prev_action = QAction("Previous", self)
        prev_action.triggered.connect(self._play_previous)
        playback_menu.addAction(prev_action)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.playlist_dock.toggleViewAction())
        view_menu.addAction(self.now_playing_dock.toggleViewAction())
        view_menu.addAction(self.spectrum_dock.toggleViewAction())
        view_menu.addAction(self.library_dock.toggleViewAction())
        view_menu.addAction(self.transport_toolbar.toggleViewAction())
        view_menu.addSeparator()

        reset_layout_action = QAction("Reset Layout", self)
        reset_layout_action.triggered.connect(self._reset_layout)
        view_menu.addAction(reset_layout_action)

    def _wire_signals(self):
        self.btn_play.clicked.connect(self._on_play_pause_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_next.clicked.connect(self._play_next)
        self.btn_prev.clicked.connect(self._play_previous)

        self.volume_slider.valueChanged.connect(self.player.set_volume)

        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)

        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playingChanged.connect(self._on_playing_changed)
        self.player.trackFinished.connect(self._play_next)

        self.model.rowsInserted.connect(self._update_status_bar)
        self.model.modelReset.connect(self._update_status_bar)

        self.player.audioSamples.connect(self.spectrum_widget.on_audio_samples)
        self.player.playingChanged.connect(self.spectrum_widget.set_active)

        self.library_widget.addTracksRequested.connect(self.model.add_paths)
        self.library_widget.playTracksRequested.connect(self._on_library_play_tracks)

    # ---- File handling ----

    def _add_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Files")
        if files:
            self.model.add_paths([Path(f) for f in files])

    def _add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Add Folder")
        if folder:
            self.model.add_paths([Path(folder)])

    def _clear_playlist(self):
        self.player.stop()
        self.model.clear()
        self.current_row = -1
        self._update_now_playing(None)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.model.add_paths(paths)

    def _on_library_play_tracks(self, paths):
        start_row = self.model.rowCount()
        self.model.add_paths(paths)
        if self.model.rowCount() > start_row:
            self._play_row(start_row)

    # ---- Playback control ----

    def _on_row_double_clicked(self, index):
        self._play_row(index.row())

    def _play_row(self, row: int):
        track = self.model.track_at(row)
        if track is None:
            return
        self.current_row = row
        self.player.load(track.path)
        self.player.play()
        self.table.selectRow(row)
        self.setWindowTitle(f"{track.artist} - {track.title}" if track.artist else track.title)
        self._update_now_playing(track)

    def _play_next(self):
        if self.model.rowCount() == 0:
            return
        next_row = self.current_row + 1
        if next_row >= self.model.rowCount():
            return
        self._play_row(next_row)

    def _play_previous(self):
        if self.model.rowCount() == 0:
            return
        prev_row = max(0, self.current_row - 1)
        self._play_row(prev_row)

    def _on_play_pause_clicked(self):
        if self.current_row == -1 and self.model.rowCount() > 0:
            self._play_row(0)
        else:
            self.player.toggle_play_pause()

    def _on_stop_clicked(self):
        self.player.stop()

    def _on_playing_changed(self, playing: bool):
        self.btn_play.setText("Pause" if playing else "Play")

    def _on_position_changed(self, position_ms: int):
        if not self._user_seeking:
            self.seek_slider.setValue(position_ms)
        self.elapsed_label.setText(format_duration(position_ms / 1000))

    def _on_duration_changed(self, duration_ms: int):
        self.seek_slider.setRange(0, duration_ms)
        self.total_label.setText(format_duration(duration_ms / 1000))

    def _on_seek_pressed(self):
        self._user_seeking = True

    def _on_seek_released(self):
        self.player.set_position(self.seek_slider.value())
        self._user_seeking = False

    def _update_status_bar(self):
        count = self.model.rowCount()
        total = format_duration(self.model.total_duration())
        self.statusBar().showMessage(f"{count} tracks, {total} total")

    def _update_now_playing(self, track):
        if track is None:
            self.np_title_label.setText("Nothing playing")
            self.np_album_label.setText("")
            return
        title_line = f"{track.artist} - {track.title}" if track.artist else track.title
        self.np_title_label.setText(title_line)
        self.np_album_label.setText(track.album)

    # ---- Layout persistence ----

    def _restore_layout(self):
        geometry = self.settings.value("layout/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.value("layout/windowState")
        if state is not None:
            self.restoreState(state)

    def _save_layout(self):
        self.settings.setValue("layout/geometry", self.saveGeometry())
        self.settings.setValue("layout/windowState", self.saveState())

    def _reset_layout(self):
        self.restoreGeometry(self._default_geometry)
        self.restoreState(self._default_state)

    def closeEvent(self, event):
        self._save_layout()
        super().closeEvent(event)
