from typing import TextIO, Any
import dataclasses
from dataclasses import dataclass
from abc import ABC, abstractmethod
import csv
import _csv

from qgis.core import QgsCoordinateReferenceSystem, QgsPointXY

from . import nspd_data
from .nspd_data import Layer, SearchObjectType, SEARCH_OBJECT_ID_TO_TYPE
from .download import ObjectDownload, ObjectDownloadPoint, ObjectDownloadObjectType
from .utils import PointXYWithCRS


@dataclass
class Parameters(ABC):
    def summary(self) -> str:
        return ''

    @abstractmethod
    def make_object_download(self) -> ObjectDownload:
        ...

    @abstractmethod
    def csv_write(self) -> list[Any]:
        ...

    @staticmethod
    def csv_read(row: list[str]) -> 'Parameters':
        if row[0] == 'object_type':
            return ParametersObjectType._csv_read(row[1:])
        if row[0] == 'point':
            return ParametersPoint._csv_read(row[1:])
        assert False, 'Неизвестный тип параметра'

    @staticmethod
    @abstractmethod
    def _csv_read(row: list[str]) -> 'Parameters':
        ...

@dataclass
class ParametersPoint(Parameters):
    layer: Layer = dataclasses.field(metadata={'name': 'Слой'})
    point_x: float = dataclasses.field(metadata={'name': 'X'})
    point_y: float = dataclasses.field(metadata={'name': 'Y'})
    point_crs: QgsCoordinateReferenceSystem = dataclasses.field(metadata={'name': 'СК'})

    def summary(self) -> str:
        return f'Точка ({self.layer.title_short()})'

    def make_object_download(self) -> ObjectDownload:
        point = PointXYWithCRS(
            QgsPointXY(self.point_x, self.point_y),
            self.point_crs,
        )
        point_transformed = point.transform_to(nspd_data.PROJECTION)
        return ObjectDownloadPoint(
            layer=self.layer,
            point_x=point_transformed.point.x(),
            point_y=point_transformed.point.y(),
        )

    def csv_write(self) -> list[Any]:
        return [
            'point',
            self.layer.id_,
            self.point_x,
            self.point_y,
            self.point_crs.authid(),
        ]

    @staticmethod
    def _csv_read(row: list[str]) -> 'Parameters':
        (
            layer_id_str,
            point_x_str,
            point_y_str,
            point_crs_authid) = row
        layer_id = int(layer_id_str)
        layer = nspd_data.layers()[layer_id]
        point_x = float(point_x_str)
        point_y = float(point_y_str)
        point_crs = QgsCoordinateReferenceSystem(point_crs_authid)  # ty:ignore[invalid-argument-type]
        return ParametersPoint(
            layer=layer,
            point_x=point_x,
            point_y=point_y,
            point_crs=point_crs,
        )

@dataclass
class ParametersObjectType(Parameters):
    search_object_type: SearchObjectType = dataclasses.field(metadata={'name': 'Вид объекта'})
    query: str = dataclasses.field(metadata={'name': 'Запрос'})

    def summary(self) -> str:
        search_object_type_str = self.search_object_type.value[1]
        return f'По виду объекта ({search_object_type_str})'

    def make_object_download(self) -> ObjectDownload:
        return ObjectDownloadObjectType(
            search_object_type=self.search_object_type,
            query=self.query,
        )

    def csv_write(self) -> list[Any]:
        return [
            'object_type',
            self.search_object_type.value[0],
            self.query,
        ]

    @staticmethod
    def _csv_read(row: list[str]) -> 'Parameters':
        search_object_type_id_str, query = row
        search_object_type_id = int(search_object_type_id_str)
        search_object_type = SEARCH_OBJECT_ID_TO_TYPE[search_object_type_id]
        return ParametersObjectType(
            search_object_type=search_object_type,
            query=query,
        )

def parameters_csv_write(parameters_list: list[Parameters], out: TextIO):
    writer = csv.writer(out, lineterminator='\n')
    for parameters in parameters_list:
        writer.writerow(parameters.csv_write())

def parameters_csv_read(in_: TextIO) -> list[Parameters]:
    parameters = []
    reader = csv.reader(in_)
    for row in reader:
        if len(row) == 0:
            continue
        parameters.append(Parameters.csv_read(row))
    return parameters

