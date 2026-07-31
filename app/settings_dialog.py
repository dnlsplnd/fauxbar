from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import spectrum
from app.player import HW_ACCEL_ENABLED_KEY

DEFAULT_VOLUME_KEY = "playback/default_volume"
CONFIRM_CLEAR_KEY = "playback/confirm_clear"
SHOW_ARTIST_KEY = "display/show_artist_in_title"


class OutputPage(QWidget):
    """foobar2000's Playback > Output page: pick which audio device to render to."""

    def __init__(self, player, settings, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)

        self.device_combo = QComboBox(self)
        self.device_combo.addItem("System Default", None)

        current_id = settings.value("playback/output_device_id")
        current_id = bytes(current_id) if current_id else None
        selected_index = 0
        for device in player.available_output_devices():
            self.device_combo.addItem(device.description(), device)
            if current_id and bytes(device.id()) == current_id:
                selected_index = self.device_combo.count() - 1
        self.device_combo.setCurrentIndex(selected_index)

        layout.addRow("Output device:", self.device_combo)

    def apply(self, player, settings):
        device = self.device_combo.currentData()
        if device is None:
            settings.remove("playback/output_device_id")
            player.set_output_device(QMediaDevices.defaultAudioOutput())
        else:
            settings.setValue("playback/output_device_id", device.id())
            player.set_output_device(device)


class PlaybackGeneralPage(QWidget):
    """foobar2000's Playback page: startup volume and a couple of behaviors."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)

        self.volume_spin = QSpinBox(self)
        self.volume_spin.setRange(0, 100)
        self.volume_spin.setSuffix("%")
        self.volume_spin.setValue(settings.value(DEFAULT_VOLUME_KEY, 80, type=int))
        layout.addRow("Default volume on startup:", self.volume_spin)

        self.confirm_clear_check = QCheckBox("Confirm before clearing the playlist", self)
        self.confirm_clear_check.setChecked(settings.value(CONFIRM_CLEAR_KEY, False, type=bool))
        layout.addRow(self.confirm_clear_check)

    def apply(self, settings):
        settings.setValue(DEFAULT_VOLUME_KEY, self.volume_spin.value())
        settings.setValue(CONFIRM_CLEAR_KEY, self.confirm_clear_check.isChecked())


class NowPlayingPage(QWidget):
    """foobar2000's Display > Now Playing page: how track titles are formatted."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.show_artist_check = QCheckBox("Show artist in window title and Now Playing panel", self)
        self.show_artist_check.setChecked(settings.value(SHOW_ARTIST_KEY, True, type=bool))
        layout.addWidget(self.show_artist_check)
        layout.addStretch()

    def apply(self, settings):
        settings.setValue(SHOW_ARTIST_KEY, self.show_artist_check.isChecked())


class SpectrumPage(QWidget):
    """foobar2000's Display > Visualisations page, scoped to the spectrum panel."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)

        self._color = QColor(settings.value(spectrum.SETTINGS_COLOR, spectrum.DEFAULT_COLOR, type=str))
        self.color_btn = QPushButton(self)
        self.color_btn.clicked.connect(self._pick_color)
        self._update_color_btn()
        layout.addRow("Bar color:", self.color_btn)

        self.brightness_spin = QSpinBox(self)
        self.brightness_spin.setRange(50, 250)
        self.brightness_spin.setSuffix("%")
        self.brightness_spin.setValue(
            settings.value(spectrum.SETTINGS_BRIGHTNESS_PERCENT, spectrum.DEFAULT_BRIGHTNESS_PERCENT, type=int)
        )
        layout.addRow("Brightness:", self.brightness_spin)

        self.bars_spin = QSpinBox(self)
        self.bars_spin.setRange(20, 200)
        self.bars_spin.setSingleStep(10)
        self.bars_spin.setValue(settings.value(spectrum.SETTINGS_BARS, spectrum.DEFAULT_BARS, type=int))
        layout.addRow("Number of bars:", self.bars_spin)

    def _pick_color(self):
        color = QColorDialog.getColor(self._color, self, "Spectrum Bar Color")
        if color.isValid():
            self._color = color
            self._update_color_btn()

    def _update_color_btn(self):
        # A stylesheet with only background-color still lets the native style
        # paint its usual button bevel/gradient over it - adding an explicit
        # border switches Qt to fully custom rendering, so the swatch shows
        # the exact color rather than a shaded approximation of it.
        self.color_btn.setText(self._color.name())
        self.color_btn.setStyleSheet(
            f"background-color: {self._color.name()}; color: #ffffff; border: 1px solid #151515;"
        )

    def apply(self, settings):
        settings.setValue(spectrum.SETTINGS_COLOR, self._color.name())
        settings.setValue(spectrum.SETTINGS_BRIGHTNESS_PERCENT, self.brightness_spin.value())
        settings.setValue(spectrum.SETTINGS_BARS, self.bars_spin.value())


class LibraryFoldersPage(QWidget):
    """foobar2000's Media Library > Folders page."""

    def __init__(self, library_widget, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.list = QListWidget(self)
        self.list.addItems(library_widget.folders())
        layout.addWidget(self.list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add...", self)
        add_btn.clicked.connect(self._add)
        remove_btn = QPushButton("Remove", self)
        remove_btn.clicked.connect(self._remove)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _add(self):
        folder = QFileDialog.getExistingDirectory(self, "Add Library Folder")
        existing = {self.list.item(i).text() for i in range(self.list.count())}
        if folder and folder not in existing:
            self.list.addItem(folder)

    def _remove(self):
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def apply(self, library_widget):
        folders = [self.list.item(i).text() for i in range(self.list.count())]
        library_widget.set_folders(folders)


class AdvancedPage(QWidget):
    """foobar2000's Advanced page: expert-level tunables, all in one flat list."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)

        self.fft_combo = QComboBox(self)
        for size in spectrum.FFT_SIZE_CHOICES:
            self.fft_combo.addItem(str(size), size)
        current_fft = settings.value(spectrum.SETTINGS_FFT_SIZE, spectrum.DEFAULT_FFT_SIZE, type=int)
        self.fft_combo.setCurrentIndex(max(self.fft_combo.findData(current_fft), 0))
        layout.addRow("Spectrum FFT size:", self.fft_combo)

        self.db_floor_spin = QSpinBox(self)
        self.db_floor_spin.setRange(-140, -40)
        self.db_floor_spin.setSuffix(" dB")
        self.db_floor_spin.setValue(
            int(settings.value(spectrum.SETTINGS_DB_FLOOR, spectrum.DEFAULT_DB_FLOOR, type=float))
        )
        layout.addRow("Spectrum noise floor:", self.db_floor_spin)

        self.attack_spin = QSpinBox(self)
        self.attack_spin.setRange(1, 200)
        self.attack_spin.setSuffix(" ms")
        self.attack_spin.setValue(settings.value(spectrum.SETTINGS_ATTACK_MS, spectrum.DEFAULT_ATTACK_MS, type=int))
        layout.addRow("Spectrum attack time:", self.attack_spin)

        self.release_spin = QSpinBox(self)
        self.release_spin.setRange(10, 2000)
        self.release_spin.setSuffix(" ms")
        self.release_spin.setValue(
            settings.value(spectrum.SETTINGS_RELEASE_MS, spectrum.DEFAULT_RELEASE_MS, type=int)
        )
        layout.addRow("Spectrum release time:", self.release_spin)

        self.peak_hold_spin = QSpinBox(self)
        self.peak_hold_spin.setRange(0, 5000)
        self.peak_hold_spin.setSuffix(" ms")
        self.peak_hold_spin.setValue(
            settings.value(spectrum.SETTINGS_PEAK_HOLD_MS, spectrum.DEFAULT_PEAK_HOLD_MS, type=int)
        )
        layout.addRow("Peak hold time:", self.peak_hold_spin)

        self.hw_accel_check = QCheckBox("Enable hardware-accelerated decoding", self)
        self.hw_accel_check.setChecked(settings.value(HW_ACCEL_ENABLED_KEY, True, type=bool))
        layout.addRow(self.hw_accel_check)

        restart_label = QLabel("Changes take effect after restarting fauxbar.")
        restart_label.setStyleSheet("color: #888888; font-style: italic;")
        layout.addRow(restart_label)

    def apply(self, settings):
        settings.setValue(spectrum.SETTINGS_FFT_SIZE, self.fft_combo.currentData())
        settings.setValue(spectrum.SETTINGS_DB_FLOOR, float(self.db_floor_spin.value()))
        settings.setValue(spectrum.SETTINGS_ATTACK_MS, self.attack_spin.value())
        settings.setValue(spectrum.SETTINGS_RELEASE_MS, self.release_spin.value())
        settings.setValue(spectrum.SETTINGS_PEAK_HOLD_MS, self.peak_hold_spin.value())
        settings.setValue(HW_ACCEL_ENABLED_KEY, self.hw_accel_check.isChecked())


class SettingsDialog(QDialog):
    """A foobar2000-style Preferences dialog: a category tree on the left
    running from basic (Playback, Display, Media Library) down to a single
    Advanced page of expert tunables, a page stack on the right, and
    OK/Cancel/Apply at the bottom."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("Preferences")
        self.resize(580, 420)

        settings = main_window.settings

        self.output_page = OutputPage(main_window.player, settings, self)
        self.playback_general_page = PlaybackGeneralPage(settings, self)
        self.now_playing_page = NowPlayingPage(settings, self)
        self.spectrum_page = SpectrumPage(settings, self)
        self.library_page = LibraryFoldersPage(main_window.library_widget, self)
        self.advanced_page = AdvancedPage(settings, self)

        self.stack = QStackedWidget(self)
        for page in (
            self.playback_general_page,
            self.output_page,
            self.now_playing_page,
            self.spectrum_page,
            self.library_page,
            self.advanced_page,
        ):
            self.stack.addWidget(page)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setFixedWidth(170)

        playback_item = QTreeWidgetItem(["Playback"])
        general_item = self._leaf("General", self.playback_general_page)
        output_item = self._leaf("Output", self.output_page)
        playback_item.addChild(general_item)
        playback_item.addChild(output_item)

        display_item = QTreeWidgetItem(["Display"])
        now_playing_item = self._leaf("Now Playing", self.now_playing_page)
        spectrum_item = self._leaf("Spectrum", self.spectrum_page)
        display_item.addChild(now_playing_item)
        display_item.addChild(spectrum_item)

        library_item = QTreeWidgetItem(["Media Library"])
        folders_item = self._leaf("Folders", self.library_page)
        library_item.addChild(folders_item)

        advanced_item = self._leaf("Advanced", self.advanced_page)

        for top in (playback_item, display_item, library_item, advanced_item):
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(self._on_tree_item_changed)
        self.tree.setCurrentItem(general_item)

        splitter = QSplitter(self)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply, self
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, stretch=1)
        layout.addWidget(buttons)

    @staticmethod
    def _leaf(label: str, page: QWidget) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.UserRole, page)
        return item

    def _on_tree_item_changed(self, current, _previous):
        if current is None:
            return
        page = current.data(0, Qt.UserRole)
        if page is not None:
            self.stack.setCurrentWidget(page)

    def _apply(self):
        settings = self.main_window.settings
        self.output_page.apply(self.main_window.player, settings)
        self.playback_general_page.apply(settings)
        self.now_playing_page.apply(settings)
        self.spectrum_page.apply(settings)
        self.library_page.apply(self.main_window.library_widget)
        self.advanced_page.apply(settings)
        self.main_window.spectrum_widget.apply_settings()

    def _on_ok(self):
        self._apply()
        self.accept()
