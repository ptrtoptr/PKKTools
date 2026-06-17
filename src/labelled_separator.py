from PyQt5.QtGui import QPalette, QColor
from typing import Optional

from PyQt5.QtWidgets import (
    QLabel,
    QSizePolicy,
    QWidget,
    QFrame,
    QHBoxLayout,
)

class LabelledSeparator(QWidget):
    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)

        line_left = QFrame(self)
        line_left.setFrameShape(QFrame.HLine)
        line_left.setFrameShadow(QFrame.Sunken)

        label = QLabel(text, self)
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)

        line_right = QFrame(self)
        line_right.setFrameShape(QFrame.HLine)
        line_right.setFrameShadow(QFrame.Sunken)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(line_left)
        layout.addWidget(label)
        layout.addWidget(line_right)

        layout.setStretch(0, 1)
        layout.setStretch(2, 1)

