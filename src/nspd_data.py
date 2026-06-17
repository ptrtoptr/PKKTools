from collections import deque
from types import NoneType
from typing import Optional, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import json
import random
import time
import textwrap

from PyQt5.QtCore import QMetaType
from qgis.core import QgsCoordinateReferenceSystem, Qgis

from .logging import LOGGER
from .utils import layer_title_short


BASE_URL = 'https://nspd.gov.ru'

WMS_RANDOM = random.random()
WMS_RANDOM_STR = str(WMS_RANDOM)

PKK_LAYER_THEME_ID: int = 1

PROJECTION_EPSG: int = 3857
PROJECTION = QgsCoordinateReferenceSystem.fromEpsgId(PROJECTION_EPSG)

@dataclass
class BaseLayer:
    id_: int
    name: str

@dataclass
class CoverageBBox:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

@dataclass
class Layer:
    id_: int
    title: str
    coverage_bbox: Optional[CoverageBBox]

    def title_short(self) -> str:
        return layer_title_short(self.title)

@dataclass
class LayerTreeNode:
    node_id: int
    title: str
    layers: list[int]
    nodes: 'list[LayerTreeNode]'

    def title_short(self) -> str:
        return layer_title_short(self.title)

class SearchObjectType(Enum):
    RealEstateObjects = (1, 'Объекты недвижимости')
    CadastralDivision = (2, 'Объекты кадастрового деления')
    AdminBoundaries  = (4, 'Объекты административно-территориального деления')
    ZonesTerritories = (5, 'Объекты слоёв зоны и территории')
    TerritorialZones = (7, 'Объекты слоя территориальные зоны')
    ObjectComplexes = (15, 'Объекты слоя Комплексы объектов')

SEARCH_OBJECT_ID_TO_TYPE: dict[int, SearchObjectType] = {
    type_.value[0]: type_ for type_ in SearchObjectType
}

FIELD_TYPE_TO_WKB: dict[type, QMetaType.Type] = {
    NoneType: QMetaType.UnknownType,
    bool: QMetaType.Bool,
    int: QMetaType.Int,
    float: QMetaType.Double,
    str: QMetaType.QString,
}

WKB_COERCION_ORDER = (
    QMetaType.UnknownType,
    QMetaType.Bool,
    QMetaType.Int,
    QMetaType.LongLong,
    QMetaType.Double,
    QMetaType.QString,
)
INT_MIN = -2**31
INT_MAX = 2**31-1

def wkb_type_from_value(value: Any) -> QMetaType.Type:
    value_type = type(value)
    if value_type is int:
        if INT_MIN <= value <= INT_MAX:
            return QMetaType.Int
        return QMetaType.LongLong
    return FIELD_TYPE_TO_WKB[type(value)]

def wkb_type_coerce(a: QMetaType.Type, b: QMetaType.Type) -> QMetaType.Type:
    if a == b:
        return a
    a_i = WKB_COERCION_ORDER.index(a)
    b_i = WKB_COERCION_ORDER.index(b)
    return WKB_COERCION_ORDER[max(a_i, b_i)]

@dataclass
class Feature:
    id_: int
    geometry: dict[str, Any]
    properties: dict[str, Any]

    def normalize(self) -> 'Feature':
        properties_data: dict[str, Any] = {}
        _feature_normalize_dict(properties_data, '', self.properties)
        return Feature(
            self.id_,
            self.geometry,
            properties_data,
        )

def _feature_normalize_dict(properties_data: dict[str, Any], path: str, properties: dict[str, Any]):
    for key, value in properties.items():
        if path == '':
            path_key = key
        else:
            path_key = f'{path}.{key}'
        if type(value) in (NoneType, bool, int, float, str):
            properties_data[path_key] = value
        elif type(value) is list:
            simple_properties_list = _feature_normalize_list(properties_data, path_key, value)
            properties_data[path_key] = ','.join(simple_properties_list)
        else:
            assert type(value) is dict, f'{path=!r}, {key=}, {value=!r}, {type(value)=!r}'
            _feature_normalize_dict(properties_data, path_key, value)

def _feature_normalize_list(
    properties_data: dict[str, Any],
    path: str,
    properties: list[Any]) -> list[str]:
    simple_properties_list: list[str] = []
    for key, value in enumerate(properties):
        if path == '':
            path_key = str(key)
        else:
            path_key = f'{path}.{key}'
        if type(value) in (NoneType, bool, int, float, str):
            simple_properties_list.append(str(value))
        elif type(value) is list:
            _feature_normalize_list(properties_data, path_key, value)
        else:
            assert type(value) is dict, f'{path=!r}, {key=}, {value=!r}, {type(value)=!r}'
            _feature_normalize_dict(properties_data, path_key, value)
    return simple_properties_list


def parts_to_features(parts: list[list[Feature]]) -> list[Feature]:
    features: list[Feature] = []
    for part in parts:
        for part_feature in part:
            feature = part_feature.normalize()
            features.append(feature)
    return features


PLUGIN_ROOT_PATH: Path = Path(__file__).parent.parent
DATA_PATH: Path = PLUGIN_ROOT_PATH/'data'/'nspd'
BASE_LAYERS_PATH: Path = DATA_PATH/'baselayers.json'
LAYERS_THEME_TREE_PATH: Path = DATA_PATH/'layers-theme-tree-1.json'
_base_layers: Optional[list[BaseLayer]] = None
_layer_tree: Optional[list[LayerTreeNode]] = None
_layers: Optional[dict[int, Layer]] = None


def load_base_layers() -> list[BaseLayer]:
    time_start = time.monotonic()

    with BASE_LAYERS_PATH.open(encoding='utf-8') as base_layers_file:
        base_layers_data = json.load(base_layers_file)
    assert type(base_layers_data) is list
    base_layers: list[BaseLayer] = []
    for base_layer_data in base_layers_data:
        assert type(base_layer_data) is dict
        id_ = base_layer_data['id']
        assert type(id_) is int
        name = base_layer_data['name']
        assert type(name) is str
        type_ = base_layer_data['type']
        assert type(name) is str
        assert type_ == 'wmts'
        base_layer = BaseLayer(
            id_=id_,
            name=name,
        )
        base_layers.append(base_layer)

    time_end = time.monotonic()
    LOGGER.info(f'Загрузили базовые слои за {time_end-time_start} с')

    return base_layers


def load_layers_full() -> tuple[list[LayerTreeNode], dict[int, Layer]]:
    time_start = time.monotonic()

    with LAYERS_THEME_TREE_PATH.open(encoding='utf-8') as base_layers_file:
        layers_theme_tree_data = json.load(base_layers_file)

    assert type(layers_theme_tree_data) is dict

    layer_tree_data = layers_theme_tree_data['tree']
    assert type(layer_tree_data) is dict
    layer_tree_folders = layer_tree_data['folders']
    assert type(layer_tree_folders) is list
    layer_tree = load_layer_tree(layer_tree_folders)

    layers_data = layers_theme_tree_data['layers']
    assert type(layers_data) is list
    layers = load_layers(layers_data)

    time_end = time.monotonic()
    LOGGER.info(f'Загрузили слои за {time_end-time_start} с')

    return (layer_tree, layers)

def _load_node(node_data: dict):
    node_id = node_data['folderId']
    assert type(node_id) is int
    title = node_data['title']
    assert type(title) is str

    layers_data = node_data['layers']
    layers = []
    if layers_data is not None:
        assert type(layers_data) is list, repr(layers_data)
        for layer_i in layers_data:
            assert type(layer_i) is int, repr(layer_i)
            layers.append(layer_i)

    nodes_data = node_data['folders']
    nodes = []
    if nodes_data is not None:
        assert type(nodes_data) is list, repr(nodes_data)
        for child_node_data in nodes_data:
            assert type(child_node_data) is dict, repr(child_node_data)
            nodes.append(_load_node(child_node_data))

    node = LayerTreeNode(
        node_id=node_id,
        title=title,
        layers=layers,
        nodes=nodes,
    )
    return node

def load_layer_tree(layer_tree_data: list) -> list[LayerTreeNode]:
    layer_tree: list[LayerTreeNode] = []
    for layer_tree_node_data in layer_tree_data:
        assert type(layer_tree_node_data) is dict
        layer_tree_node = _load_node(layer_tree_node_data)
        layer_tree.append(layer_tree_node)

    return layer_tree

def load_layers(layers_data: list) -> dict[int, Layer]:
    layers: dict[int, Layer] = {}
    for layer_data in layers_data:
        assert type(layer_data) is dict
        layer_id = layer_data['layerId']
        assert type(layer_id) is int
        title = layer_data['title']
        assert type(title) is str
        coverage_data = layer_data.get('coverage')
        coverage_bbox = None
        if coverage_data is not None:
            assert type(coverage_data) is dict
            coverage_bbox_data = coverage_data['bbox']
            assert type(coverage_bbox_data) is list

            x_min = coverage_bbox_data[0]
            assert type(x_min) is float
            y_min = coverage_bbox_data[1]
            assert type(y_min) is float
            x_max = coverage_bbox_data[2]
            assert type(x_max) is float
            y_max = coverage_bbox_data[3]
            assert type(y_max) is float

            coverage_bbox = CoverageBBox(x_min, y_min, x_max, y_max)

        layer = Layer(
            id_=layer_id,
            title=title,
            coverage_bbox=coverage_bbox,
        )
        layers[layer_id] = layer

    return layers


def base_layers() -> list[BaseLayer]:
    global _base_layers
    if _base_layers is None:
        _base_layers = load_base_layers()
    return _base_layers

def layer_tree() -> list[LayerTreeNode]:
    global _layer_tree, _layers
    if _layer_tree is None:
        _layer_tree, _layers = load_layers_full()
    return _layer_tree

def layers() -> dict[int, Layer]:
    global _layer_tree, _layers
    if _layers is None:
        _layer_tree, _layers = load_layers_full()
    return _layers

