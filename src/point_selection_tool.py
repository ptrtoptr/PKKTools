from typing import Optional

from qgis.gui import (
    QgsMapCanvas,
    QgsMapTool,
    QgsMapMouseEvent,
    QgsSnapIndicator)

from qgis.core import QgsPointLocator

from PyQt5.QtCore import (
    Qt,
    pyqtSignal,
    QPoint)

from .utils import PointXYWithCRS


# Инструмент (как, например, инструмент перемещения по карте или выделения объектов), который вызывает сигнал
# с точкой на карте, куда нажал пользователь. Частично скопировано с инструмента привязки растра.
# См. https://github.com/qgis/QGIS/blob/15a77662d4bb712184f6aa60d0bd663010a76a75/src/app/georeferencer/qgsmapcoordsdialog.cpp
class PointSelectionTool(QgsMapTool):
    point_selected = pyqtSignal(PointXYWithCRS)

    snap_indicator: QgsSnapIndicator

    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.snap_indicator = QgsSnapIndicator(canvas)
    
    def _snap_point_to_map(self, point: QPoint):
        converted_point = self.toMapCoordinates(point)
        canvas = self.canvas()
        assert canvas is not None
        snappingUtils = canvas.snappingUtils()
        assert snappingUtils is not None
        return snappingUtils.snapToMap(converted_point)

    # Вызывается когда двигается курсор по карте
    def canvasMoveEvent(self, e: Optional[QgsMapMouseEvent]):
        assert e is not None
        self.snap_indicator.setMatch(self._snap_point_to_map(e.pos()))
    
    # Вызывается когда отпускается кнопка мыши
    def canvasReleaseEvent(self, e: Optional[QgsMapMouseEvent]):
        assert e is not None
        if e.button() == Qt.RightButton:
            self.deactivate()
        if e.button() != Qt.LeftButton:
            return
        m = self._snap_point_to_map(e.pos())
        point = m.point() if m.isValid() else self.toMapCoordinates(e.pos())
        canvas = self.canvas()
        assert canvas is not None
        crs = canvas.mapSettings().destinationCrs()
        self.point_selected.emit(PointXYWithCRS(point, crs))
        self.deactivate()

    # Вызывается когда этот инструмент меняется на другой
    def deactivate(self):
        self.snap_indicator.setMatch(QgsPointLocator.Match())
        super().deactivate()

