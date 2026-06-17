import typing
from typing import Any, Optional, Union
from abc import ABC, abstractmethod
import dataclasses
from dataclasses import dataclass

from PyQt5.QtCore import (
    Qt,
    QObject,
    QModelIndex,
    QAbstractItemModel,
)
from PyQt5.QtWidgets import QMessageBox

from qgis.core import QgsCoordinateReferenceSystem

from .logging import LOGGER
from .nspd_data import Layer, SearchObjectType
from .parameters import Parameters
from .download import ObjectDownload


def model_index_to_str(model_index: QModelIndex):
    internal_pointer = None
    if model_index.isValid():
        internal_pointer = model_index.internalPointer()
    return f'QModelIndex({model_index.row()}, {model_index.column()}, {internal_pointer})'

class ParametersTreeItem(ABC):
    _data: list[Any]
    _children: 'Optional[list[ParametersTreeItem]]' = None

    def __init__(self, parent_item: 'Optional[ParametersTreeItem]', data: Optional[list[Any]] = None):
        self.parent_item = parent_item
        self._data = data if data is not None else []

    def __repr__(self) -> str:
        values = vars(self).copy()
        values.pop('parent_item', None)
        values.pop('_children', None)
        values_str = ', '.join(f'{k}={v}' for k, v in values.items())
        return f'{self.__class__.__name__}({values_str})'

    def __init_children(self) -> 'list[ParametersTreeItem]':
        _children: list[Optional[ParametersTreeItem]] = [None] * self._child_count()
        row = -1
        for row in range(len(_children)):
            child = self._child_item(row)
            _children[row] = child
        assert row == len(_children)-1
        return _children # type: ignore
    
    def _init_children(self):
        self._children = self.__init_children()
    
    def children(self) -> 'list[ParametersTreeItem]':
        if self._children is None:
            self._children = self.__init_children()
        return self._children

    @abstractmethod
    def _child_count(self) -> int:
        ...

    @abstractmethod
    def _child_item(self, row: int) -> 'ParametersTreeItem':
        ...

    def column_count(self) -> int:
        return len(self._data)

    def child_count(self) -> int:
        if self._children is None:
            return self._child_count()
        return len(self._children)

    def child_item(self, row: int) -> 'Optional[ParametersTreeItem]':
        children = self.children()
        if 0 <= row < len(children):
            return children[row]
        return None

    def insert_child(self, row: int):
        self.children().insert(row, self._child_item(row))

    def remove_child(self, row: int):
        del self.children()[row]
    
    def remove_children(self, start: int, end: int):
        del self.children()[start:end]

    def row(self) -> int:
        if self.parent_item is None:
            return -1
        return self.parent_item.children().index(self)
    
    def data(self, column: int, role: int = Qt.DisplayRole) -> Any:
        if role != Qt.DisplayRole:
            return None
        if column < len(self._data):
            return self._data[column]
    
    def set_data(self, value: Any, role: int) -> bool:
        return False

class ParametersTreeItemRoot(ParametersTreeItem):
    parameters: list[Parameters]

    def __init__(self, parameters: list[Parameters]):
        super().__init__(None, data=['Параметр', 'Значение'])
        self.parameters = parameters
        self._init_children()

    def _child_count(self) -> int:
        return len(self.parameters)

    def _child_item(self, row: int) -> 'ParametersTreeItem':
        return ParametersTreeItemParameters(self, self.parameters[row])

    def insert_parameters(self, row: int, parameters: Parameters):
        self.parameters.insert(row, parameters)
        self.insert_child(row)

    def remove_parameters(self, row: int) -> Parameters:
        parameters = self.parameters[row]
        del self.parameters[row]
        self.remove_child(row)
        return parameters

    def remove_parameters_span(self, start: int, end: int):
        del self.parameters[start:end]
        self.remove_children(start, end)

class ParametersTreeItemParameters(ParametersTreeItem):
    parameters: Parameters

    def __init__(self, parent_item: ParametersTreeItemRoot, parameters: Parameters):
        super().__init__(parent_item, [parameters.summary()])
        self.parameters = parameters
        self._init_children()

    def _child_count(self) -> int:
        return len(dataclasses.fields(self.parameters))

    def _child_item(self, row: int) -> 'ParametersTreeItem':
        fields = dataclasses.fields(self.parameters)
        field = fields[row]
        name = field.metadata.get('name', field.name)
        data = getattr(self.parameters, field.name)
        return ParametersTreeItemParameter(self, name, data)

class ParametersTreeItemParameter(ParametersTreeItem):
    def __init__(self, parent_item: ParametersTreeItemParameters, name: str, data: Any):
        super().__init__(parent_item, data=[name, data])
        self._init_children()

    def _child_count(self) -> int:
        return 0

    def _child_item(self, row: int) -> 'ParametersTreeItem':
        assert False

class ParametersTreeModel(QAbstractItemModel):
    _root_item: ParametersTreeItemRoot

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._root_item = ParametersTreeItemRoot([])

    def rootItem(self) -> ParametersTreeItem:
        return self._root_item
    
    def indexToItem(self, index: QModelIndex) -> ParametersTreeItem:
        if not index.isValid():
            return self.rootItem()
        item_any = index.internalPointer()
        assert isinstance(item_any, ParametersTreeItem)
        return item_any

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._root_item.data(section)
        return None

    def index(self, row: int, column: int, parent: QModelIndex) -> QModelIndex: # type: ignore[override] # ty:ignore[invalid-method-override]
        # if not self.hasIndex(row, column, parent):
        #     return QModelIndex()
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()

        parent_item = self.indexToItem(parent)

        child_item = parent_item.child_item(row)
        if child_item is None:
            return QModelIndex()

        return self.createIndex(row, column, child_item)
    
    def parent(self, child: QModelIndex) -> QModelIndex: # type: ignore[override] # ty:ignore[invalid-method-override]
        if not child.isValid():
            return QModelIndex()

        child_item = self.indexToItem(child)
        parent_item = child_item.parent_item
        if parent_item is None or parent_item is self.rootItem():
            return QModelIndex()
        return self.createIndex(parent_item.row(), 0, parent_item)
    
    def rowCount(self, parent: QModelIndex) -> int: # type: ignore[override] # ty:ignore[invalid-method-override]
        if parent.isValid() and parent.column() > 0:
            return 0
        parent_item = self.indexToItem(parent)
        child_count = parent_item.child_count()
        return child_count

    def columnCount(self, parent: QModelIndex) -> int: # type: ignore[override] # ty:ignore[invalid-method-override]
        # parent_item = self.indexToItem(parent)
        # return parent_item.column_count()
        return self.rootItem().column_count()

    def _dataRender(self, data: Any) -> Any:
        if isinstance(data, float):
            return str(data)
        if isinstance(data, SearchObjectType):
            return data.value[1]
        if isinstance(data, Layer):
            return data.title
        if isinstance(data, QgsCoordinateReferenceSystem):
            return data.authid()
        return data

    def data(self, proxyIndex: QModelIndex, role: int = Qt.DisplayRole) -> Any: # type: ignore[override] # ty:ignore[invalid-method-override]
        if not proxyIndex.isValid() or role != Qt.DisplayRole:
            return None
        item = self.indexToItem(proxyIndex)
        data = item.data(proxyIndex.column(), role)
        return self._dataRender(data)
    
    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False
        item = self.indexToItem(index)
        was_set = item.set_data(value, role)
        if was_set:
            self.dataChanged.emit(index, index, [role])
        return was_set

    def parameters(self) -> list[Parameters]:
        return self._root_item.parameters
    
    def insertParameters(self, row: int, parameters: Parameters) -> None:
        if row > len(self._root_item.parameters):
            row = len(self._root_item.parameters)
        self.beginInsertRows(QModelIndex(), row, row)
        self._root_item.insert_parameters(row, parameters)
        self.endInsertRows()
    
    def appendParameters(self, parameters: Parameters) -> None:
        self.insertParameters(len(self._root_item.parameters), parameters)
    
    def removeParameters(self, row: int) -> Optional[Parameters]:
        if row >= len(self._root_item.parameters):
            return None
        self.beginRemoveRows(QModelIndex(), row, row)
        parameters = self._root_item.remove_parameters(row)
        self.endRemoveRows()
        return parameters
    
    def removeParametersSpan(self, row_start: int, row_end: int):
        self.beginRemoveRows(QModelIndex(), row_start, row_end-1)
        self._root_item.remove_parameters_span(row_start, row_end)
        self.endRemoveRows()
        return True

    def clear(self):
        self.removeParametersSpan(0, len(self.parameters()))
    
    def removeRows(self, row: int, count: int, parent: QModelIndex) -> bool: # type: ignore[override] # ty:ignore[invalid-method-override]
        if parent.isValid():
            return False
        self.removeParametersSpan(row, row+count)
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlags(Qt.NoItemFlags)
        return Qt.ItemFlag.ItemIsEnabled \
            | Qt.ItemFlag.ItemIsSelectable
            # | Qt.ItemFlag.ItemIsEditable

