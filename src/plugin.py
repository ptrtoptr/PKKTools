# ruff: noqa: E501

import traceback
import sys
import time
import gc
from typing import Optional, TypeVar, Any
from dataclasses import dataclass
from enum import Enum
import ssl
import urllib.error
import urllib.parse
import urllib.request
import json
from pathlib import Path
from json import JSONDecodeError
import logging

# Импорты QGIS
from qgis.gui import (
    QgisInterface,
    QgsMapCanvas
    , QgsMapTool
    , QgsMapMouseEvent
    , QgsSnapIndicator
    , QgsProjectionSelectionWidget)

import qgis.utils
from qgis.core import (
    QgsNetworkAccessManager,
    QgsProject
    , QgsPointXY
    , QgsPointLocator
    , QgsCoordinateReferenceSystem
    , QgsCoordinateTransform, QgsVectorLayer, QgsJsonUtils, QgsFeature, QgsField, Qgis, QgsVectorFileWriter, QgsFields, QgsFeatureSink, QgsWkbTypes, QgsMemoryProviderUtils, QgsVectorLayerUtils)


# Импорты PYQT5
import PyQt5.sip as sip
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QUrl, QSettings, QMetaType
from PyQt5.QtWidgets import (
    QWidget
    , QLabel
    , QPushButton
    , QCheckBox
    , QLineEdit
    , QAction
    , QAbstractItemView
    , QAbstractScrollArea
    , QTableWidget
    , QTableWidgetItem

    , QMessageBox
    , QDialog
    , QInputDialog
    , QDialogButtonBox
    
    , QHBoxLayout
    , QVBoxLayout
    , QFormLayout, QToolBar)


from .utils import pkk_type_to_name, qwidget_remove_parent
from .logging import LOGGER, setup_logger
from .settings import get_settings
from . import download
from .point_selection_tool import PointSelectionTool
from .point_selection_button import PointSelectionButton
from .parameters_dialog import ParametersDialog, Submission
from .parameters_model import Parameters
from .metadata import PLUGIN_NAME
from .download import ObjectDownloads, ObjectDownloadBatch, ObjectDownloadPoint, ObjectDownloadObjectType, ObjectDownloadWithBatch
from . import nspd_data
from .nspd_data import Feature, PROJECTION_EPSG, parts_to_features, wkb_type_coerce, wkb_type_from_value


# Функция вызывается в одном месте при нажатии кнопки "Перезагрузить PKKTools" которая перезагружает сам плагин.
def reload_this_plugin():
    LOGGER.info('Перезагружаем плагин')
    qgis.utils.reloadPlugin(PLUGIN_NAME)

# Главный класс плагина. Отвечает за загрузку, разгрузку плагина.
class PKKToolsPlugin:
    iface: QgisInterface

    parameters_dialog: Optional[ParametersDialog] = None

    toolbar: QToolBar
    action_reload: QAction
    action_parameters_dialog: QAction
    actions: list[QAction]

    downloads: ObjectDownloads

    # Выполняется в функции classFactory, создает сам класс
    def __init__(self, iface: QgisInterface):
        self.iface = iface
        network = QgsNetworkAccessManager.instance()
        assert network is not None
        self.downloads = ObjectDownloads(network=network)

    # Выполняется, как и __init__, при загрузке плагина
    def initGui(self):
        setup_logger(PLUGIN_NAME)

        LOGGER.info(f'Загружен плагин')

        toolbar = self.iface.addToolBar(PLUGIN_NAME)
        assert toolbar is not None
        self.toolbar = toolbar
        self.toolbar.setObjectName(PLUGIN_NAME)

        self.action_reload = QAction(f'Перезагрузить {PLUGIN_NAME}', self.iface.mainWindow())
        self.action_reload.triggered.connect(reload_this_plugin)

        self.action_parameters_dialog = QAction(f'{PLUGIN_NAME}', self.iface.mainWindow())
        self.action_parameters_dialog.triggered.connect(self.show_parameters_dialog)

        self.actions = [
            self.action_reload,
            self.action_parameters_dialog,
        ]
        for action in self.actions:
            self.toolbar.addAction(action)

    # Выполняется при разгрузке плагина
    def unload(self):
        for action in self.actions:
            self.toolbar.removeAction(action)

    def show_parameters_dialog(self):
        if self.parameters_dialog is not None:
            if self.parameters_dialog.isVisible():
                self.parameters_dialog.activateWindow()
                return
            qwidget_remove_parent(self.parameters_dialog)
            self.parameters_dialog = None

        map_canvas = self.iface.mapCanvas()
        assert map_canvas is not None
        parameters_dialog = ParametersDialog(map_canvas, self.iface.mainWindow())
        parameters_dialog.submit_parameters.connect(self._parameters_submitted)
        parameters_dialog.finished.connect(self.after_parameters_dialog)
        self.parameters_dialog = parameters_dialog
        parameters_dialog.show()
        parameters_dialog.activateWindow()
    
    def after_parameters_dialog(self, is_accepted: int):
        if self.parameters_dialog is None:
            return
        qwidget_remove_parent(self.parameters_dialog)
        self.parameters_dialog = None
    
    def _parameters_submitted(self, submission: Submission):
        LOGGER.info(f'PKKToolsPlugin._parameters_submitted: {submission}')
        batch = ObjectDownloadBatch(
            num_parts=len(submission.parameters),
            should_load_incomplete_layers=get_settings().load_incomplete_layers,
            should_load_attributes=submission.should_load_attributes,
            layer_path=submission.layer_path,
            layer_name='nspd',
            should_load_layer=submission.should_load_layer,
        )
        batch.finished.connect(self._batch_finished)
        for part_i, parameters in enumerate(submission.parameters):
            object_download = parameters.make_object_download()
            part = ObjectDownloadWithBatch(batch, part_i, object_download)
            self.downloads.add(part)
    
    def _load_layer_memory(
            self,
            project: QgsProject,
            layer_name: str,
            features: list[QgsFeature],
            geometry_type: Qgis.WkbType,
            fields: QgsFields) -> QgsVectorLayer:
        layer = QgsMemoryProviderUtils.createMemoryLayer(
            layer_name,
            fields,
            geometry_type,
            nspd_data.PROJECTION,
        )
        assert layer is not None
        layer.startEditing()
        wereFeaturesAdded = layer.addFeatures(features)
        layer.commitChanges(True)
        if not wereFeaturesAdded:
            LOGGER.warning('Объекты не добавлены')
        return layer
    
    def _load_layer_persistent(
            self,
            project: QgsProject,
            layer_path: Path,
            layer_name: str,
            features: list[QgsFeature],
            geometry_type: Qgis.WkbType,
            fields: QgsFields,
            should_load_layer: bool) -> Optional[QgsVectorLayer]:
        layer_filename = str(layer_path)
        file_extension = layer_path.suffix
        save_vector_options = QgsVectorFileWriter.SaveVectorOptions()
        save_vector_options.driverName = QgsVectorFileWriter.driverForExtension(file_extension)
        writer = QgsVectorFileWriter.create(
            layer_filename,
            fields,
            geometry_type,
            nspd_data.PROJECTION,
            project.transformContext(),
            save_vector_options,
            QgsFeatureSink.SinkFlags(),
            layer_filename,
        )
        assert writer is not None
        writer.addFeatures(features)
        writer.finalize()
        del writer
        
        if should_load_layer:
            return QgsVectorLayer(
                layer_filename,
                layer_name,
                'ogr')
        else:
            return None

    def _display_errors(self, errors: list[Exception]):
        messages = []
        for error in errors:
            messages.append(f'{error}')
        QMessageBox.critical(
            self.iface.mainWindow(),
            'PKKTools: Ошибка загрузки',
            '\n'.join(messages))

    def _batch_finished(self, batch: ObjectDownloadBatch, parts: Optional[list[list[Feature]]], errors: list[Exception]):
        LOGGER.info('Завершен пакет запросов')

        if parts is None:
            assert errors
            self._display_errors(errors)
            return

        project = QgsProject.instance()
        assert project is not None

        layer_path = batch.layer_path()
        
        features = parts_to_features(parts)
        if len(features) <= 0:
            LOGGER.info('Без объектов')
            if errors:
                self._display_errors(errors)
            return

        SEPARATORS = (',', ':')

        fields_dict: dict[str, QgsField] = {}
        for feature in features:
            properties = feature.properties
            for field_name, field_value in properties.items():
                if field_value is None:
                    continue
                field_type = wkb_type_from_value(field_value)
                if field_name in fields_dict:
                    existing_field = fields_dict[field_name]
                    existing_field_type = existing_field.type()
                    coerced_field_type = wkb_type_coerce(existing_field_type, field_type)
                    if coerced_field_type != existing_field_type:
                        LOGGER.debug(
                            f'Поле {field_name!r}: ' \
                            f'Конвертация типов: ' \
                            f'{QMetaType.typeName(existing_field_type)} .. ' \
                            f'{QMetaType.typeName(field_type)} == ' \
                            f'{QMetaType.typeName(coerced_field_type)}'
                        )
                        existing_field.setType(coerced_field_type)
                    continue
                field = QgsField(
                    field_name,  # ty:ignore[invalid-argument-type]
                    field_type,  # ty:ignore[too-many-positional-arguments]
                )
                fields_dict[field_name] = field

        fields = QgsFields(list(fields_dict.values()))

        geometry_type: Optional[Qgis.WkbType] = None
        qgs_features = []
        geometry_mismatch_count: int = 0
        for feature in features:
            feature_geometry_data = feature.geometry
            feature_geometry_str = json.dumps(feature_geometry_data, separators=SEPARATORS, ensure_ascii=False)
            feature_geometry = QgsJsonUtils.geometryFromGeoJson(feature_geometry_str)
            feature_geometry_type = feature_geometry.wkbType()
            if geometry_type is None:
                geometry_type = feature_geometry_type
            elif feature_geometry_type != geometry_type:
                geometry_mismatch_count += 1
                continue
            properties = feature.properties
            qgs_feature = QgsFeature(fields, feature.id_)
            qgs_feature.setGeometry(feature_geometry)
            attributes: list[Any] = [None for _ in range(len(fields))]
            for field_i, (field_name, field) in enumerate(fields_dict.items()):
                attributes[field_i] = properties.get(field_name, None)
            qgs_feature.setAttributes(attributes)
            qgs_features.append(qgs_feature)
        assert geometry_type is not None
        if geometry_mismatch_count > 0:
            LOGGER.warning(f'Пропустили {geometry_mismatch_count} из {len(features)} объектов из-за несовпадения типа геометрии (TODO)')
        
        layer: Optional[QgsVectorLayer]
        if layer_path is not None:
            layer = self._load_layer_persistent(
                project,
                layer_path,
                batch.layer_name(),
                qgs_features,
                geometry_type,
                fields,
                batch.should_load_layer(),
            )
        elif batch.should_load_layer():
            layer = self._load_layer_memory(
                project,
                batch.layer_name(),
                qgs_features,
                geometry_type,
                fields,
            )
        
        if layer is not None:
            project.addMapLayer(layer)
        
        if errors:
            self._display_errors(errors)


