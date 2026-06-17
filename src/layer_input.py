from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from typing import Optional
from dataclasses import dataclass

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QComboBox

from . import nspd_data
from .nspd_data import Layer, LayerTreeNode
from .utils import layer_title_short


@dataclass
class Level:
    layers: list[Layer]
    nodes: list[LayerTreeNode]
    combo_box: QComboBox

    def _add_item(self, title: str, prefix: str, title_short: str):
        item_i = self.combo_box.count()
        self.combo_box.addItem(prefix+title_short)
        if title_short != title:
            self.combo_box.setItemData(item_i, title, Qt.ToolTipRole)

    def __init__(self, layers: list[Layer], nodes: list[LayerTreeNode]):
        self.layers = layers
        self.nodes = nodes
        self.combo_box = QComboBox()
        self.combo_box.addItem('')
        for layer in self.layers:
            self._add_item(layer.title, '', layer.title_short())
        for node in self.nodes:
            self._add_item(node.title, '▼ ', node.title_short())


class LayerInput(QWidget):
    layer_changed = pyqtSignal(object)

    _layers: dict[int, Layer]
    _nodes: list[LayerTreeNode]
    
    _levels: list[Level]
    _main_layout: QVBoxLayout

    _selected_layer: Optional[Layer] = None

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._layers = nspd_data.layers()
        self._nodes = nspd_data.layer_tree()
        self._levels = []
        self._main_layout = QVBoxLayout(self)

        level = Level([], self._nodes)
        self._level_append(level)

    def selected_layer(self) -> Optional[Layer]:
        return self._selected_layer
    
    def _level_append(self, level: Level):
        level_i = len(self._levels)
        self._levels.append(level)
        self._main_layout.addWidget(level.combo_box)
        level.combo_box.currentIndexChanged.connect(self._index_changed(level_i))

    def _index_changed(self, level_i: int):
        def index_changed(index: int):
            selected_layer_old = self._selected_layer
            self._selected_layer = None
            level = self._levels[level_i]
            for item_i in range(len(self._levels), level_i, -1):
                self._main_layout.takeAt(item_i)
            del self._levels[level_i+1:]
            
            index_found = False
            if index < 1:
                index_found = True
            if not index_found:
                index -= 1
                if index < len(level.layers):
                    self._selected_layer = level.layers[index]
                    index_found = True
            if not index_found:
                index -= len(level.layers)
                if index < len(level.nodes):
                    node = level.nodes[index]
                    layers = [self._layers[layer_id] for layer_id in node.layers]
                    self._level_append(Level(layers, node.nodes))
                    index_found = True
            assert index_found
            if selected_layer_old is not self._selected_layer:
                self.layer_changed.emit(self._selected_layer)
        return index_changed

