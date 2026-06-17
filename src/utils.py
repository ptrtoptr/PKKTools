from dataclasses import dataclass
from typing import Optional
import textwrap

from PyQt5.QtWidgets import QWidget

from qgis.core import (
    QgsPointXY,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    CoordinateTransformationFlags,
)


def qwidget_remove_parent(widget: QWidget):
    widget.setParent(None) # type: ignore


def layer_title_short(title: str):
    return textwrap.shorten(title, width=50, placeholder='…')


@dataclass
class PointXYWithCRS:
    point: QgsPointXY
    crs: QgsCoordinateReferenceSystem

    def transform_to(self, target_crs: QgsCoordinateReferenceSystem) -> 'PointXYWithCRS':
        if self.crs == target_crs:
            return self
        transform = QgsCoordinateTransform(
            self.crs, # ty:ignore[invalid-argument-type]
            target_crs, # ty:ignore[too-many-positional-arguments]
            QgsProject.instance(),
            CoordinateTransformationFlags(),
        )
        transformed_point = transform.transform(self.point)
        return PointXYWithCRS(transformed_point, target_crs)


# Отображение номера слоя к его названию
pkk_type_to_name = {
    1: 'Участки',
    2: 'Кварталы',
    3: 'Районы',
    4: 'Округа',
    5: 'ОКС',
    6: 'Территориальные зоны',
    7: 'Границы',
    10: 'ЗОУИТ',
    13: 'Красные линии',
    15: 'Проекты ЗУ',
    20: 'Зоны и территории',
    23: 'Негативные процессы',
    24: 'Комплексы',
    25: 'Земля для стройки',
    26: 'Усолье-Сибирское',
    27: 'Земля для туризма',
    28: 'Объект туристического интереса',
}

# Порядок имен слоев в ПКК, который показывается пользователю
pkk_name_order = [
    'Участки',
    'ОКС',
    'Комплексы',
    'Проекты ЗУ',
    'Земля для стройки',
    'Земля для туризма',
    'Объект туристического интереса',
    'Кварталы',
    'Районы',
    'Округа',
    'ЗОУИТ',
    'Зоны и территории',
    'Территориальные зоны',
    'Красные линии',
    'Границы',
    'Негативные процессы',
    'Усолье-Сибирское',
]

# Название слоя в его номер, упорядочены по номеру
pkk_name_to_type_ordered_by_type = {}
t = n = None
for t, n in pkk_type_to_name.items():
    assert n not in pkk_name_to_type_ordered_by_type
    pkk_name_to_type_ordered_by_type[n] = t

# Название слоя в его номер, упорядочены по именам слоев - то, что нам нужно.
pkk_name_to_type = {}
for n in pkk_name_order:
    assert n not in pkk_name_to_type
    pkk_name_to_type[n] = pkk_name_to_type_ordered_by_type[n]

del t, n, pkk_name_to_type_ordered_by_type

