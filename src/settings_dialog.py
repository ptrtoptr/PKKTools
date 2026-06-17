import dataclasses
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QFormLayout, QCheckBox, QSpinBox, QButtonGroup, QRadioButton, QDialogButtonBox, QHBoxLayout

from .settings import Settings
from .logging import LOGGER


class SettingsDialog(QDialog):
    _settings: Settings

    def __init__(self, settings: Settings, parent = None):
        super().__init__(parent)

        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        self.setWindowTitle('PKKTools: Настройки')

        self._unmodified_settings = settings
        self._settings = dataclasses.replace(settings)
        
        self._load_incomplete_layers = QCheckBox('Загрузка неполных слоёв')
        self._load_incomplete_layers.setChecked(settings.load_incomplete_layers)
        self._load_incomplete_layers.stateChanged.connect(self._on_load_incomplete_layers)

        INT_MAX = (1 << 31) - 1

        self._max_parallel_downloads = QSpinBox()
        self._max_parallel_downloads.setMinimum(1)
        self._max_parallel_downloads.setMaximum(INT_MAX)
        self._max_parallel_downloads.setSingleStep(1)
        self._max_parallel_downloads.setValue(settings.max_parallel_downloads)
        self._max_parallel_downloads.valueChanged.connect(self._on_max_parallel_downloads)

        self._delay_between_requests_ms = QSpinBox()
        self._delay_between_requests_ms.setMinimum(0)
        self._delay_between_requests_ms.setMaximum(INT_MAX)
        self._delay_between_requests_ms.setSingleStep(500)
        self._delay_between_requests_ms.setValue(settings.delay_between_requests_ms)
        self._delay_between_requests_ms.valueChanged.connect(self._on_delay_between_requests_ms)

        self._transfer_timeout_default = QRadioButton('Как в QGIS')
        self._transfer_timeout_custom = QRadioButton('Установленное')
        self._transfer_timeout_selection = QButtonGroup(self)
        self._transfer_timeout_selection.addButton(self._transfer_timeout_default)
        self._transfer_timeout_selection.addButton(self._transfer_timeout_custom)
        transfer_timeout_layout = QHBoxLayout()
        transfer_timeout_layout.addWidget(self._transfer_timeout_default)
        transfer_timeout_layout.addWidget(self._transfer_timeout_custom)
        if settings.transfer_timeout_ms is None:
            self._transfer_timeout_default.setChecked(True)
        else:
            self._transfer_timeout_custom.setChecked(True)
        self._transfer_timeout_default.toggled.connect(self._on_transfer_timeout_checkbox)
        self._transfer_timeout_custom.toggled.connect(self._on_transfer_timeout_checkbox)

        self._transfer_timeout_ms = QSpinBox()
        self._transfer_timeout_ms.setMinimum(0)
        self._transfer_timeout_ms.setMaximum(INT_MAX)
        self._transfer_timeout_ms.setSingleStep(1000)
        if settings.transfer_timeout_ms is None:
            self._transfer_timeout_ms.hide()
            self._transfer_timeout_ms.setValue(0)
        else:
            self._transfer_timeout_ms.setValue(settings.transfer_timeout_ms)
        self._transfer_timeout_ms.valueChanged.connect(self._on_transfer_timeout_ms)
    
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        self._main_layout = QFormLayout(self)
        self._main_layout.addRow(self._load_incomplete_layers)
        self._main_layout.addRow('Количество параллельных запросов', self._max_parallel_downloads)
        self._main_layout.addRow('Задержка между запросами, мс', self._delay_between_requests_ms)
        self._main_layout.addRow('Время ожидания запроса, мс', transfer_timeout_layout)
        self._main_layout.addRow(self._transfer_timeout_ms)
        self._main_layout.addRow(button_box)

    def _on_load_incomplete_layers(self):
        self._settings.load_incomplete_layers = self._load_incomplete_layers.isChecked()
    
    def _on_max_parallel_downloads(self):
        self._settings.max_parallel_downloads = self._max_parallel_downloads.value()

    def _on_delay_between_requests_ms(self):
        self._settings.delay_between_requests_ms = self._delay_between_requests_ms.value()

    def _on_transfer_timeout_checkbox(self):
        if self._transfer_timeout_default.isChecked():
            self._settings.transfer_timeout_ms = None
            self._transfer_timeout_ms.hide()
            self._transfer_timeout_ms.setValue(0)
        else:
            self._settings.transfer_timeout_ms = 0
            self._transfer_timeout_ms.setValue(0)
            self._transfer_timeout_ms.show()

    def _on_transfer_timeout_ms(self):
        self._settings.transfer_timeout_ms = self._transfer_timeout_ms.value()

    def done(self, a0: int):
        result_code = a0
        if result_code:
            for field in dataclasses.fields(self._settings):
                name = field.name
                value = getattr(self._settings, name)
                setattr(self._unmodified_settings, name, value)
            self._unmodified_settings.save()
        return super().done(result_code)

