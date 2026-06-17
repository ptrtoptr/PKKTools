from typing import Optional

from PyQt5.QtCore import Qt, QModelIndex
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QTreeView, QHeaderView, QWidget


class ParametersTreeView(QTreeView):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.header().setSectionResizeMode(QHeaderView.ResizeToContents)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() != Qt.Key.Key_Delete:
            return super().keyPressEvent(event)
        model = self.model()
        if model is None:
            return
        selection = self.selectionModel()
        if selection is None:
            return
        root = QModelIndex()
        rows = [index.row() for index in selection.selectedRows() if not index.parent().isValid()]
        rows.sort(reverse=True)
        row_start = None
        row_end = None
        for row in rows:
            if row_start is None or row_end is None:
                row_start = row_end = row
                continue
            if row+1 == row_start:
                row_start = row
                continue
            model.removeRows(row_start, row_end-row_start+1, root)
            row_start = row_end = row
        if row_start is not None and row_end is not None:
            model.removeRows(row_start, row_end-row_start+1, root)

