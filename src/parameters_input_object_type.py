from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QFormLayout,
)

from . import nspd_data
from .parameters import ParametersObjectType

class ParametersInputObjectType(QWidget):
    add_parameters = pyqtSignal(ParametersObjectType)

    _search_object_type_input: QComboBox
    _query_input: QLineEdit
    _error_message_label: QLabel

    _layout_main: QFormLayout

    _parameters: Optional[ParametersObjectType] = None

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._search_object_type_input = QComboBox()
        self._search_object_type_input.addItem('')
        for search_object_type in nspd_data.SearchObjectType:
            self._search_object_type_input.addItem(search_object_type.value[1])
        self._search_object_type_input.currentIndexChanged.connect(self._search_object_type_input_update)

        self._query_input = QLineEdit()
        self._query_input.textEdited.connect(self._query_input_update)

        self._error_message_label = QLabel()
        palette = self._error_message_label.palette()
        palette.setColor(self._error_message_label.foregroundRole(), Qt.red)
        self._error_message_label.setPalette(palette)

        add_button = QPushButton('Добавить')
        add_button.clicked.connect(self._add_parameters)

        self._layout_main = QFormLayout(self)
        
        self._layout_main.addRow('Вид объекта', self._search_object_type_input)
        self._layout_main.addRow('Запрос', self._query_input)
        self._layout_main.addRow(self._error_message_label)
        self._layout_main.addRow(add_button)
    
    def parameters(self) -> Optional[ParametersObjectType]:
        return self._parameters
    
    def _update_parameters(self) -> str:
        search_object_type_index = self._search_object_type_input.currentIndex() - 1
        if search_object_type_index < 0:
            self._parameters = None
            return 'Не выбран вид объекта'
        query = self._query_input.text()
        if query == '':
            self._parameters = None
            return 'Не введен запрос'
        search_object_type = list(nspd_data.SearchObjectType)[search_object_type_index]
        self._parameters = ParametersObjectType(search_object_type, query)
        return ''

    def _search_object_type_input_update(self, search_object_type_index: int):
        self._update_parameters()

    def _query_input_update(self, query_number: str):
        self._update_parameters()

    def _add_parameters(self):
        error = self._update_parameters()
        if error != '':
            self._error_message_label.setText(error)
            return
        self._error_message_label.setText('')
        assert self._parameters is not None
        parameters= self._parameters
        self._parameters = None
        self._query_input.clear()
        self.add_parameters.emit(parameters)
