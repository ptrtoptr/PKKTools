from qgis.gui import QgsMapCanvas

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QPushButton

from .utils import PointXYWithCRS
from .point_selection_tool import PointSelectionTool


# Кнопка выбора точки на карте
class PointSelectionButton(QPushButton):
    selection_start = pyqtSignal()
    selection_end = pyqtSignal(object) # возвращает PointXYWithCRS или None если был отменен инструмент

    def __del__(self):
        self._selection_end_cancelled()

    def __init__(self, map_canvas: QgsMapCanvas, parent=None):
        super().__init__('Выбор с карты...', parent)

        self.map_canvas = map_canvas
        self.point_selection_tool = None
        self.old_map_tool = None

        self.clicked.connect(self._try_select_point_from_map)

    def _is_selecting(self):
        return self.point_selection_tool is not None

    def _try_select_point_from_map(self):
        if self.point_selection_tool is None:
            assert self.old_map_tool is None

            self.point_selection_tool = PointSelectionTool(self.map_canvas)
            self.point_selection_tool.deactivated.connect(self._selection_end_cancelled)
            self.point_selection_tool.point_selected.connect(self._selection_end_selected)

            self.old_map_tool = self.map_canvas.mapTool()

            self.map_canvas.setMapTool(self.point_selection_tool)

            self.selection_start.emit()
        else:
            self.map_canvas.setMapTool(self.point_selection_tool)
        
    def _unset_map_tool(self):
        if self.point_selection_tool is not None:
            self.point_selection_tool = None
            self.map_canvas.setMapTool(self.old_map_tool)
            self.old_map_tool = None
    
    def _selection_end_selected(self, point: PointXYWithCRS):
        assert self.point_selection_tool is not None
        self._unset_map_tool()
        self.selection_end.emit(point)
    
    def _selection_end_cancelled(self):
        if self.point_selection_tool is None:
            return
        assert self.map_canvas.mapTool() == self.point_selection_tool

        self._unset_map_tool()
        self.selection_end.emit(None)

