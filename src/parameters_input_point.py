from typing import Optional, Union
from enum import Enum

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QDialogButtonBox,
    QFormLayout,
    QPushButton, QComboBox,
)

from qgis.core import QgsPointXY, QgsCoordinateReferenceSystem
from qgis.gui import QgsMapCanvas, QgsProjectionSelectionWidget

from .utils import qwidget_remove_parent, PointXYWithCRS
from . import nspd_data
from .layer_input import LayerInput
from .point_selection_button import PointSelectionButton
from .parameters import ParametersPoint


class ParametersInputPoint(QWidget):
    add_parameters = pyqtSignal(ParametersPoint)

    # FIXME: QGis вылетает при закрытии окна QGis когда открыт этот диалог
    _selected_point_xy: Optional[QgsPointXY] = None
    _selected_point_crs: Optional[QgsCoordinateReferenceSystem] = None

    map_canvas: QgsMapCanvas

    layer_input: LayerInput
    click_coordinate_input: PointSelectionButton
    manual_coordinate_input: QLineEdit
    projection_selection: QgsProjectionSelectionWidget
    error_message_label: QLabel

    layout_main: QFormLayout


    def _selected_point_valid(self) -> bool:
        return self._selected_point_xy is not None and self._selected_point_crs is not None

    def __del__(self):
        qwidget_remove_parent(self.click_coordinate_input)
        del self.click_coordinate_input
    
    # Наверное самая длинная функция в плагине.
    # Разбирает строку, введенную в текстовое поле ввода координат в, собственно, сами координаты.
    def _parse_selected_point_xy(self) -> Union[QgsPointXY, str]:
        States = Enum('States',
             ['START'
            , 'X_MIDDLE'
            , 'AFTER_X'
            , 'AFTER_COMMA'
            , 'Y_MIDDLE'
            , 'AFTER_Y'], start=0)
        ACCEPTING_STATES = [States.Y_MIDDLE, States.AFTER_Y]
        
        def is_float_char(char):
            # Если символ один из '+-_0123456789.eE'
            return not char.isspace() and char != ','
        
        generic_error_message = 'Координаты должны быть введены в форме "X, Y" или "X Y"'
        state = States.START
        text = self.manual_coordinate_input.text()
        x_str = ''
        y_str = ''
        for char in text:
            if state == States.START:
                if is_float_char(char):
                    x_str += char
                    state = States.X_MIDDLE
                elif char.isspace():
                    state = States.START
                else:
                    return generic_error_message

            elif state == States.X_MIDDLE:
                if is_float_char(char):
                    x_str += char
                    state = States.X_MIDDLE
                elif char.isspace():
                    state = States.AFTER_X
                elif char == ',':
                    state = States.AFTER_COMMA
                else:
                    return generic_error_message

            elif state == States.AFTER_X:
                if is_float_char(char):
                    y_str += char
                    state = States.Y_MIDDLE
                elif char.isspace():
                    state = States.AFTER_X
                elif char == ',':
                    state = States.AFTER_COMMA
                else:
                    return generic_error_message

            elif state == States.AFTER_COMMA:
                if is_float_char(char):
                    y_str += char
                    state = States.Y_MIDDLE
                elif char.isspace():
                    state = States.AFTER_COMMA
                else:
                    return generic_error_message
            
            elif state == States.Y_MIDDLE:
                if is_float_char(char):
                    y_str += char
                    state = States.Y_MIDDLE
                elif char.isspace():
                    state = States.AFTER_Y
                else:
                    return generic_error_message

            elif state == States.AFTER_Y:
                if char.isspace():
                    state = States.AFTER_Y
                else:
                    return generic_error_message
            
            else:
                raise ValueError('Unknown state')

        if state not in ACCEPTING_STATES:
            return generic_error_message
        
        try:
            x = float(x_str)
        except ValueError:
            return 'Неправильное значение координаты X'
        
        try:
            y = float(y_str)
        except ValueError:
            return 'Неправильное значение координаты Y'
        
        return QgsPointXY(x, y)

    def set_error_message(self, message):
        self.error_message_label.setText(message)

    def update_error_message(self):
        self.error_message_label.setVisible(not self._selected_point_valid())

    def _update_selected_point_xy(self):
        point_or_error = self._parse_selected_point_xy()
        if isinstance(point_or_error, QgsPointXY):
            self._selected_point_xy = point_or_error
        else:
            self._selected_point_xy = None
            self.set_error_message(point_or_error)
        self.update_error_message()
            
    def _update_selected_point_crs(self):
        crs = self.projection_selection.crs()
        self._selected_point_crs = crs if crs.isValid() else None
        if not crs.isValid():
            self.set_error_message('Неправильная система координат')
        self.update_error_message()

    @property
    def selected_point(self) -> Optional[PointXYWithCRS]:
        if self._selected_point_valid():
            assert self._selected_point_xy is not None
            assert self._selected_point_crs is not None
            return PointXYWithCRS(self._selected_point_xy, self._selected_point_crs)
        return None

    @selected_point.setter
    def selected_point(self, new_point: Optional[PointXYWithCRS]):
        if new_point is None:
            self._selected_point_xy = None
            self._selected_point_crs = None
            coordinates_text = ''
            crs = self.map_canvas.mapSettings().destinationCrs()
        else:
            point_xy = new_point.point
            self._selected_point_xy = point_xy
            self._selected_point_crs = new_point.crs
            coordinates_text = point_xy.toString()
            crs = self._selected_point_crs
            
        self.manual_coordinate_input.setText(coordinates_text)
        self.projection_selection.setCrs(crs)
        self.update_error_message()
    
    def selection_end(self, point: Optional[PointXYWithCRS]):
        if point is None:
            return
        self.selected_point = point
        self.activateWindow()

    def _add_point(self):
        selected_layer = self.layer_input.selected_layer()
        if selected_layer is None:
            return
        selected_point = self.selected_point
        if selected_point is None:
            return
        parameters = ParametersPoint(
            layer=selected_layer,
            point_x=selected_point.point.x(),
            point_y=selected_point.point.y(),
            point_crs=selected_point.crs,
        )
        self.manual_coordinate_input.clear()
        self._selected_point_xy = None
        self.add_parameters.emit(parameters)

    def __init__(self, map_canvas: QgsMapCanvas, parent = None):
        super().__init__(parent)

        self.layer_input = LayerInput()

        self.map_canvas = map_canvas

        layer_type_id_input = QComboBox()
        for node in nspd_data.layer_tree():
            layer_type_id_input.addItem('')
        layer_id_input = QComboBox()

        self.click_coordinate_input = PointSelectionButton(map_canvas)
        self.click_coordinate_input.selection_end.connect(self.selection_end)

        self.manual_coordinate_input = QLineEdit()
        self.manual_coordinate_input.textEdited.connect(self._update_selected_point_xy)

        self.projection_selection = QgsProjectionSelectionWidget()
        self.projection_selection.setMinimumWidth(320)
        self.projection_selection.crsChanged.connect(self._update_selected_point_crs)

        self.error_message_label = QLabel()
        palette = self.error_message_label.palette()
        palette.setColor(self.error_message_label.foregroundRole(), Qt.red)
        self.error_message_label.setPalette(palette)

        add_point_button = QPushButton('Добавить')
        add_point_button.clicked.connect(self._add_point)

        self.layout_main = QFormLayout(self)

        self.layout_main.addRow(self.layer_input)
        self.layout_main.addRow(self.click_coordinate_input)
        self.layout_main.addRow("Координаты (X, Y)", self.manual_coordinate_input)
        self.layout_main.addRow("Система координат", self.projection_selection)
        self.layout_main.addRow(self.error_message_label)
        self.layout_main.addRow(add_point_button)
        
        self.selected_point = None


