from io import StringIO
from pathlib import Path
import typing
from abc import ABC, abstractmethod
import dataclasses
from dataclasses import dataclass
from typing import Optional, Union, ClassVar, Any
from enum import Enum

import qgis.processing
from qgis.gui import (
    QgsMapCanvas,
    QgsProjectionSelectionWidget,
    QgsProcessingLayerOutputDestinationWidget,
    QgsGui, QgisInterface,
)
from qgis.core import (
    QgsPointXY,
    QgsCoordinateReferenceSystem,
    QgsProcessingParameterFeatureSink,
    Qgis, QgsProperty, QgsExpressionContext,
)

from PyQt5.QtCore import Qt, QAbstractItemModel, QObject, QModelIndex, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QFrame,
    QLabel,
    QLineEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QTableWidget,
    QPushButton,
    QListWidget,
    QHBoxLayout,
    QListWidgetItem,
    QTreeView,
    QButtonGroup,
    QRadioButton,
    QTabWidget,
    QCheckBox,
    QSizePolicy, QApplication, QFileDialog,
)
from PyQt5.QtTest import QAbstractItemModelTester

from .utils import PointXYWithCRS, qwidget_remove_parent
from .logging import LOGGER
from .labelled_separator import LabelledSeparator
from .settings_dialog import SettingsDialog
from .parameters import Parameters, parameters_csv_write, parameters_csv_read
from .parameters_model import ParametersTreeModel
from .parameters_view import ParametersTreeView
from .parameters_input_object_type import ParametersInputObjectType
from .parameters_input_point import ParametersInputPoint
from .feature_sink_widget_wrapper import FeatureSinkWidgetWrapper
from .settings import get_settings


@dataclass
class Submission:
    parameters: list[Parameters]
    should_load_attributes: bool
    layer_path: Optional[Path]
    should_load_layer: bool

# Диалог выбора точки
class ParametersDialog(QDialog):
    submit_parameters = pyqtSignal(Submission)

    _settings_dialog: Optional[SettingsDialog] = None
    _parameters_tree_model: ParametersTreeModel
    _should_load_attributes_input: QCheckBox
    _layout_main: QFormLayout

    def __init__(self, map_canvas: QgsMapCanvas, parent = None):
        super().__init__(parent)

        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        self.setWindowTitle('PKKTools: Выбор параметров')

        parameters_input_object_type = ParametersInputObjectType()
        parameters_input_object_type.add_parameters.connect(self._add_parameters)

        parameters_input_point = ParametersInputPoint(map_canvas)
        parameters_input_point.add_parameters.connect(self._add_parameters)

        parameters_tabs = QTabWidget()
        parameters_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        parameters_tabs.addTab(parameters_input_object_type, 'Вид объекта')
        parameters_tabs.addTab(parameters_input_point, 'Точка')


        self._parameters_tree_model = ParametersTreeModel(self)

        parameters_tree_view = ParametersTreeView()
        parameters_tree_view.setModel(self._parameters_tree_model)


        parameters_buttons = QHBoxLayout()
        parameters_button_copy = QPushButton('Копировать')
        parameters_button_copy.clicked.connect(self._parameters_copy)
        parameters_button_save = QPushButton('Сохранить')
        parameters_button_save.clicked.connect(self._parameters_save)
        parameters_button_paste = QPushButton('Вставить')
        parameters_button_paste.clicked.connect(self._parameters_paste)
        parameters_button_load = QPushButton('Загрузить')
        parameters_button_load.clicked.connect(self._parameters_load)
        parameters_buttons.addWidget(parameters_button_copy)
        parameters_buttons.addWidget(parameters_button_save)
        parameters_buttons.addWidget(parameters_button_paste)
        parameters_buttons.addWidget(parameters_button_load)

        self._should_load_attributes_input = QCheckBox('Загрузка атрибутов')
        self._should_load_attributes_input.setChecked(True)
        
        self._output_feature_sink_input_wrapper = FeatureSinkWidgetWrapper(
            'OUTPUT',
            'Выходной слой',
            Qgis.ProcessingSourceType.VectorAnyGeometry
        )
        self._output_feature_sink_input = self._output_feature_sink_input_wrapper.widget()

        load_button = QPushButton('Загрузить')
        load_button.clicked.connect(self._load_start)

        settings_button = QPushButton('Настройки')
        settings_button.clicked.connect(self._settings_dialog_open)

        button_box = QDialogButtonBox(QDialogButtonBox.Close, self)
        button_box.addButton(load_button, QDialogButtonBox.ActionRole)
        button_box.addButton(settings_button, QDialogButtonBox.ActionRole)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        self._layout_main = QFormLayout(self)
        
        self._layout_main.addRow(parameters_tabs)

        self._layout_main.addRow(LabelledSeparator('Выбранные параметры'))
        self._layout_main.addRow(parameters_tree_view)
        self._layout_main.addRow(parameters_buttons)
        self._layout_main.addRow(LabelledSeparator('Слой'))
        self._layout_main.addRow(self._should_load_attributes_input)
        self._layout_main.addRow(self._output_feature_sink_input)

        self._layout_main.addRow(button_box)

    def done(self, a0: int):
        result_code = a0
        if not result_code:
            return super().done(result_code)

    def _add_parameters(self, parameters: Parameters):
        self._parameters_tree_model.appendParameters(parameters)

    def _parameters_copy(self):
        parameters = self._parameters_tree_model.parameters()
        out = StringIO()
        parameters_csv_write(parameters, out)
        clipboard = QApplication.clipboard()
        clipboard.setText(out.getvalue())

    def _parameters_save(self):
        parameters = self._parameters_tree_model.parameters()
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            'Сохранение CSV параметров',
            '',
            'CSV Files (*.csv)')
        if not filename:
            return
        with open(filename, 'w', encoding='utf-8') as out:
            parameters_csv_write(parameters, out)

    def _parameters_paste(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        in_ = StringIO(text)
        parameters_list = parameters_csv_read(in_)
        for parameters in parameters_list:
            self._parameters_tree_model.appendParameters(parameters)

    def _parameters_load(self):
        filename, selected_filter = QFileDialog.getOpenFileName(
            self,
            'Открытие CSV параметров',
            '',
            'CSV Files (*.csv)')
        if not filename:
            return
        with open(filename, encoding='utf-8') as in_:
            parameters_list = parameters_csv_read(in_)
            for parameters in parameters_list:
                self._parameters_tree_model.appendParameters(parameters)

    def _load_start(self) -> None:
        parameters = self._parameters_tree_model.parameters()
        if len(parameters) == 0:
            return
        parameter_value = self._output_feature_sink_input_wrapper.parameter_value()
        sink_property: QgsProperty = parameter_value.sink
        sink = sink_property.staticValue()
        assert type(sink) is str
        layer_path = None
        if sink != 'TEMPORARY_OUTPUT':
            layer_path = Path(sink)
        load_layer_checkbox = self._output_feature_sink_input.findChild(QCheckBox)
        assert load_layer_checkbox is not None
        should_load_layer = load_layer_checkbox.isChecked()
        if layer_path is None and not should_load_layer:
            # Загружать временный слой который не должен быть добавлен в проект бессмысленно
            return
        submission = Submission(
            parameters=parameters,
            should_load_attributes=self._should_load_attributes_input.isChecked(),
            layer_path=layer_path,
            should_load_layer=should_load_layer,
        )
        self.submit_parameters.emit(submission)
        self._parameters_tree_model.clear()
    
    def _settings_dialog_open(self):
        if self._settings_dialog is not None:
            if self._settings_dialog.isVisible():
                self._settings_dialog.activateWindow()
                return
            qwidget_remove_parent(self._settings_dialog)
            self._settings_dialog = None
        settings_dialog = SettingsDialog(get_settings(), parent=self.parent())
        settings_dialog.finished.connect(self._settings_dialog_finished)
        self._settings_dialog = settings_dialog
        settings_dialog.show()
        settings_dialog.activateWindow()

    def _settings_dialog_finished(self):
        self._settings_dialog = None

