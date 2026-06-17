from dataclasses import dataclass
from typing import Optional

from qgis.core import QgsNetworkAccessManager, QgsSettings

from .metadata import SETTINGS_PREFIX
from .logging import LOGGER


SETTING_LOAD_INCOMPLETE_LAYERS = f'{SETTINGS_PREFIX}/loadIncompleteLayers'
SETTING_MAX_PARALLEL_DOWNLOADS = f'{SETTINGS_PREFIX}/maxParallelDownloads'
SETTING_DELAY_TIMEOUT_BETWEEN_REQUESTS_MS = f'{SETTINGS_PREFIX}/delayTimeoutBetweenRequestsMs'
SETTING_TRANSFER_TIMEOUT_MS = f'{SETTINGS_PREFIX}/transferTimeoutMs'

@dataclass
class Settings:
    qgs_settings: QgsSettings
    load_incomplete_layers: bool = True
    max_parallel_downloads: int = 1
    delay_between_requests_ms: int = 1000
    transfer_timeout_ms: Optional[int] = None

    @staticmethod
    def load(qgs_settings: QgsSettings) -> 'Settings':
        load_incomplete_layers = qgs_settings.value(
            SETTING_LOAD_INCOMPLETE_LAYERS,
            None)
        if load_incomplete_layers is None:
            load_incomplete_layers = Settings.load_incomplete_layers
        elif type(load_incomplete_layers) is bool:
            pass
        elif load_incomplete_layers == 'false':
            load_incomplete_layers = False
        elif load_incomplete_layers == 'true':
            load_incomplete_layers = True
        else:
            assert False, repr(load_incomplete_layers)

        max_parallel_downloads=qgs_settings.value(
            SETTING_MAX_PARALLEL_DOWNLOADS,
            None)
        if max_parallel_downloads is None:
            max_parallel_downloads = Settings.max_parallel_downloads
        elif type(max_parallel_downloads) is int:
            pass
        else:
            max_parallel_downloads = int(max_parallel_downloads)

        delay_between_requests_ms=qgs_settings.value(
            SETTING_DELAY_TIMEOUT_BETWEEN_REQUESTS_MS,
            None)
        if delay_between_requests_ms is None:
            delay_between_requests_ms = Settings.delay_between_requests_ms
        elif type(delay_between_requests_ms) is int:
            pass
        else:
            delay_between_requests_ms = int(delay_between_requests_ms)

        transfer_timeout_ms=qgs_settings.value(
            SETTING_TRANSFER_TIMEOUT_MS,
            None)
        if transfer_timeout_ms is None:
            transfer_timeout_ms = Settings.transfer_timeout_ms
        elif type(transfer_timeout_ms) is int:
            pass
        else:
            transfer_timeout_ms = int(transfer_timeout_ms)

        settings = Settings(
            qgs_settings=qgs_settings,
            load_incomplete_layers=load_incomplete_layers,
            max_parallel_downloads=max_parallel_downloads,
            delay_between_requests_ms=delay_between_requests_ms,
            transfer_timeout_ms=transfer_timeout_ms,
        )

        LOGGER.info(f'Загружены настройки {settings}')

        return settings

    def save(self):
        self.qgs_settings.setValue(SETTING_LOAD_INCOMPLETE_LAYERS, self.load_incomplete_layers)
        self.qgs_settings.setValue(SETTING_MAX_PARALLEL_DOWNLOADS, self.max_parallel_downloads)
        self.qgs_settings.setValue(SETTING_DELAY_TIMEOUT_BETWEEN_REQUESTS_MS, self.delay_between_requests_ms)
        self.qgs_settings.setValue(SETTING_TRANSFER_TIMEOUT_MS, self.transfer_timeout_ms)
        LOGGER.info(f'Сохранены настройки {self}')

_settings: Optional[Settings] = None
def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.load(qgs_settings=QgsSettings())
    return _settings

