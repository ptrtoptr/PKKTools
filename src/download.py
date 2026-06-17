from collections import deque
from dataclasses import dataclass
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Callable, Optional, Any
from abc import ABC, abstractmethod

from PyQt5.QtCore import QUrl, QUrlQuery, pyqtSignal, QTimer, QObject
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qgis.core import QgsNetworkAccessManager, QgsPointXY, QgsRectangle

from .logging import LOGGER
from .settings import get_settings
from .nspd_data import BASE_URL, WMS_RANDOM_STR, SearchObjectType, Layer, Feature


def get(network: QNetworkAccessManager, url: QUrl) -> QNetworkReply:
    request = QNetworkRequest(url)
    settings = get_settings()

    url_str = url.toString(QUrl.FullyEncoded) # type: ignore[arg-type]
    url_bytes = url_str.encode('utf-8')
    request.setRawHeader(b'Referer', url_bytes)

    if settings.transfer_timeout_ms is not None:
        request.setTransferTimeout(settings.transfer_timeout_ms)

    LOGGER.info(f'GET {url_str}')

    return network.get(request)

class ReplyErrorNetwork(Exception):
    url: str
    error: QNetworkReply.NetworkError
    error_str: str
    def __init__(self, url: str, error: QNetworkReply.NetworkError, error_str: str):
        self.url = url
        self.error = error
        self.error_str = error_str
    def __repr__(self) -> str:
        return f'ReplyErrorNetwork(url={self.url!r}, error={self.error!r}, error_str={self.error_str!r})'
    def __str__(self) -> str:
        return self.__repr__()
    @staticmethod
    def from_reply(reply: QNetworkReply) -> 'Optional[ReplyErrorNetwork]':
        error: QNetworkReply.NetworkError = reply.error() # type: ignore
        assert isinstance(error, QNetworkReply.NetworkError)
        if error == QNetworkReply.NetworkError.NoError:
            return None
        return ReplyErrorNetwork(
            url=reply.url().toString(),
            error=reply.error(), # type: ignore
            error_str=reply.errorString(),
        )

class ReplyErrorHTTP(Exception):
    url: str
    status_code: int
    message: str
    headers: dict[str, str]
    def __init__(self, url: str, status_code: int, message: str, headers: dict[str, str]):
        self.url = url
        self.status_code = status_code
        self.message = message
        self.headers = headers
    def __repr__(self) -> str:
        return \
            f'ReplyErrorHTTP(' \
            f'url={self.url!r}, ' \
            f'status_code={self.status_code!r}, ' \
            f'message={self.message!r}, ' \
            f'headers={self.headers!r})'
    def __str__(self) -> str:
        return self.__repr__()
    @staticmethod
    def from_reply(reply: QNetworkReply) -> 'Optional[ReplyErrorHTTP]':
        status_code = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        if status_code is None:
            return None
        assert type(status_code) is int
        if status_code == 200:
            return None
        data = reply.readAll()
        text = data.data().decode('utf-8')
        headers = {
            key.data().decode('ascii'): value.data().decode('ascii')
            for key, value in reply.rawHeaderPairs()
        }
        raise ReplyErrorHTTP(
            reply.url().toString(),
            status_code,
            text,
            headers,
        )

def reply_check_error(reply: QNetworkReply) -> None:
    error_http = ReplyErrorHTTP.from_reply(reply)
    if error_http is not None:
        raise error_http
    error_network = ReplyErrorNetwork.from_reply(reply)
    if error_network is not None:
        raise error_network

def reply_text(reply: QNetworkReply) -> str:
    reply_check_error(reply)
    data = reply.readAll()
    text = data.data().decode('utf-8')
    return text

def reply_json(reply: QNetworkReply) -> Any:
    text = reply_text(reply)
    try:
        return json.loads(text)
    except JSONDecodeError as e:
        LOGGER.error(f'Ошибка разбора JSON: {e}. Текст: {text!r}')
        raise e

class FeaturesReply(ABC):
    inner: QNetworkReply

    def __init__(self, inner: QNetworkReply):
        self.inner = inner
    
    def text(self) -> str:
        return reply_text(self.inner)
    
    def json(self) -> Any:
        return reply_json(self.inner)

    @abstractmethod
    def _features(self) -> list[Any]:
        ...

    def features(self) -> list[Feature]:
        features = self._features()
        for feature_i, feature_data in enumerate(features):
            if isinstance(feature_data, Feature):
                continue
            assert type(feature_data) is dict
            id_ = feature_data['id']
            assert type(id_) is int
            geometry = feature_data['geometry']
            assert type(geometry) is dict
            properties = feature_data['properties']
            assert type(properties) is dict
            feature = Feature(
                id_=id_,
                geometry=geometry,
                properties=properties,
            )
            features[feature_i] = feature
        return features

class ObjectDownloadBatch(QObject):
    finished = pyqtSignal(object, object, object)

    _parts: list[Optional[list[Feature]]]
    _errors: list[Exception]
    _num_complete_parts: int = 0
    _should_load_incomplete_layers: bool
    _should_load_attributes: bool
    _layer_path: Optional[Path]
    _layer_name: str
    _should_load_layer: bool
    _is_finished: bool = False

    def __init__(
            self,
            num_parts: int,
            should_load_incomplete_layers: bool,
            should_load_attributes: bool,
            layer_path: Optional[Path],
            layer_name: str,
            should_load_layer: bool,
            parent: Optional[QObject] = None):
        super().__init__(parent)
        self._parts = [None for _ in range(num_parts)]
        self._errors = []
        self._should_load_incomplete_layers = should_load_incomplete_layers
        self._should_load_attributes = should_load_attributes
        self._layer_name = layer_name
        self._layer_path = layer_path
        self._should_load_layer = should_load_layer
    
    def layer_path(self) -> Optional[Path]:
        return self._layer_path
    
    def layer_name(self) -> str:
        return self._layer_name
    
    def should_load_layer(self) -> bool:
        return self._should_load_layer

    def on_part_done(self, part_i: int, part: list[Feature], error: Optional[Exception]) -> bool:
        if self._is_finished:
            LOGGER.debug(f'Отвержен ответ запроса, пришедший после завершения пакета запросов. {part_i=!r} {error=!r}')
            return False
        old_part = self._parts[part_i]
        assert old_part is None
        if error is not None:
            LOGGER.error(f'Ошибка при скачивании или разборе ответа {part_i=}: {error!r}')
            self._errors.append(error)
        should_keep_data = error is None or self._should_load_incomplete_layers
        if should_keep_data and not self._should_load_attributes:
            for data in part:
                data.properties = {}
        if not should_keep_data:
            self._is_finished = True
            self.finished.emit(self, None, self._errors)
            return False
        self._parts[part_i] = part
        self._num_complete_parts += 1
        if self._num_complete_parts >= len(self._parts):
            assert self._num_complete_parts == len(self._parts)
            for part_ in self._parts:
                assert part_ is not None
            self._is_finished = True
            self.finished.emit(self, self._parts, self._errors)
        return True

class ObjectDownload(ABC):
    @abstractmethod
    def request(self, network: QgsNetworkAccessManager) -> FeaturesReply:
        ...

def features_from_collection(feature_collection: Any) -> list:
    assert type(feature_collection) is dict
    assert feature_collection['type'] == 'FeatureCollection'
    features = feature_collection['features']
    assert type(features) is list
    return features

class FeaturesReplyPoint(FeaturesReply):
    def _features(self) -> list[Any]:
        reply_data = self.json()
        features = features_from_collection(reply_data)
        return features

class ObjectDownloadPoint(ObjectDownload):
    layer: Layer
    point_x: float
    point_y: float

    def __init__(self, layer: Layer, point_x: float, point_y: float):
        self.layer = layer
        self.point_x = point_x
        self.point_y = point_y
    
    def request(self, network: QgsNetworkAccessManager) -> FeaturesReply:
        layer_id_str = str(self.layer.id_)
        bbox = f'{self.point_x},{self.point_y},{self.point_x+0.001},{self.point_y+0.001}'
        query = QUrlQuery()
        query.addQueryItem('REQUEST', 'GetFeatureInfo')
        query.addQueryItem('QUERY_LAYERS', layer_id_str)
        query.addQueryItem('SERVICE', 'WMS')
        query.addQueryItem('VERSION', '1.3.0')
        query.addQueryItem('FORMAT', 'image/png')
        query.addQueryItem('STYLES', '')
        query.addQueryItem('TRANSPARENT', 'true')
        query.addQueryItem('LAYERS', layer_id_str)
        query.addQueryItem('RANDOM', WMS_RANDOM_STR)
        query.addQueryItem('INFO_FORMAT', 'application/json')
        query.addQueryItem('FEATURE_COUNT', '10')
        query.addQueryItem('I', '0')
        query.addQueryItem('J', '0')
        query.addQueryItem('WIDTH', '1')
        query.addQueryItem('HEIGHT', '1')
        query.addQueryItem('CRS', 'EPSG:3857')
        query.addQueryItem('BBOX', bbox)
        url = QUrl(f'{BASE_URL}/api/aeggis/v4/{layer_id_str}/wms')
        url.setQuery(query)
        reply = get(network, url)
        return FeaturesReplyPoint(reply)


class FeaturesReplyObjectType(FeaturesReply):
    def _features(self) -> list[Any]:
        reply_data = self.json()
        assert type(reply_data) is dict
        data = reply_data['data']
        features = features_from_collection(data)
        return features

class ObjectDownloadObjectType(ObjectDownload):
    search_object_type: SearchObjectType
    query: str

    def __init__(self, search_object_type: SearchObjectType, query: str):
        self.search_object_type = search_object_type
        self.query = query
    
    def request(self, network: QgsNetworkAccessManager) -> FeaturesReply:
        thematic_id_str = str(self.search_object_type.value[0])
        query = QUrlQuery()
        query.addQueryItem('thematicSearchId', thematic_id_str)
        query.addQueryItem('query', self.query)
        url = QUrl(f'{BASE_URL}/api/geoportal/v2/search/geoportal')
        url.setQuery(query)
        reply = get(network, url)
        return FeaturesReplyObjectType(reply)

@dataclass
class ObjectDownloadWithBatch:
    batch: ObjectDownloadBatch
    i: int
    download: ObjectDownload

    def on_done(self, data: list[Feature], error: Optional[Exception]) -> bool:
        return self.batch.on_part_done(self.i, data, error)

class ObjectDownloads:
    _network: QgsNetworkAccessManager
    _queued: deque[ObjectDownloadWithBatch]
    _max_in_progress: int
    _in_progress: dict[FeaturesReply, ObjectDownloadWithBatch]

    def __init__(self, network: QgsNetworkAccessManager):
        self._network = network
        self._queued = deque()
        self._max_in_progress = get_settings().max_parallel_downloads
        self._in_progress = dict()

    def add(self, download: ObjectDownloadWithBatch):
        self._queued.appendleft(download)
        self._update()

    def remove_batch(self, batch: ObjectDownloadBatch) -> bool:
        removed_anything = False
        for reply, in_progress_download in self._in_progress.copy().items():
            if in_progress_download.batch is batch:
                LOGGER.debug(f'Удаляем и останавливаем выполняющийся запрос {in_progress_download!r}')
                self._in_progress.pop(reply, None)
                reply.inner.abort()
                removed_anything = True

        new_queued: deque[ObjectDownloadWithBatch] = deque()
        for queued_download in self._queued:
            if queued_download.batch is not batch:
                new_queued.append(queued_download)
            else:
                LOGGER.debug(f'Удаляем запрос в очереди {queued_download=!r}')
                removed_anything = True
        self._queued = new_queued
        return removed_anything

    def _reply_finished_slot(self, part: ObjectDownloadWithBatch, reply: FeaturesReply):
        def reply_finished():
            self._reply_finished(part, reply)
        return reply_finished

    def _update(self):
        settings = get_settings()
        self._max_in_progress = settings.max_parallel_downloads
        while len(self._in_progress) < self._max_in_progress:
            try:
                part = self._queued.pop()
            except IndexError:
                return
            reply = part.download.request(self._network)
            old_reply = self._in_progress.setdefault(reply, part)
            assert old_reply is not reply
            reply.inner.finished.connect(self._reply_finished_slot(part, reply))
    
    def _reply_finished(self, part: ObjectDownloadWithBatch, reply: FeaturesReply):
        LOGGER.debug(f'Завершен запрос: {part=!r}')
        features = []
        error: Optional[Exception] = None
        try:
            features = reply.features()
        except Exception as e:
            error = e
        is_batch_uninterrupted = False
        try:
            is_batch_uninterrupted = part.on_done(features, error)
        finally:
            self._in_progress.pop(reply, None)
            if not is_batch_uninterrupted:
                LOGGER.debug(f'Удаляем пакет запросов {part.batch!r}')
                removed_anything = self.remove_batch(part.batch)
                if removed_anything:
                    LOGGER.debug(f'Удалили пакет запросов {part.batch!r}')
            settings = get_settings()
            if settings.delay_between_requests_ms > 0:
                QTimer.singleShot(settings.delay_between_requests_ms, self._update)
            else:
                self._update()

