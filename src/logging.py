import logging
from typing import Dict
import sys

from qgis.core import Qgis, QgsMessageLog


PLUGIN_NAME = 'PKKTools'

LEVEL_STR_TO_QGIS: Dict[str, Qgis.MessageLevel] = {
      'NOTSET': Qgis.MessageLevel.NoLevel,
       'DEBUG': Qgis.MessageLevel.Info,
        'INFO': Qgis.MessageLevel.Info,
     'WARNING': Qgis.MessageLevel.Warning,
       'ERROR': Qgis.MessageLevel.Critical,
    'CRITICAL': Qgis.MessageLevel.Critical,
}

class QgsLogHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        logging.Handler.__init__(self)

    def emit(self, record):
        QgsMessageLog.logMessage(
            record.getMessage(),
            PLUGIN_NAME,
            LEVEL_STR_TO_QGIS[record.levelname])

class StreamHandler(logging.StreamHandler):
    def __init__(self, stream):
        assert stream is not None
        super().__init__(stream)

def setup_root_logger():
    if sys.stderr is None:
        return

    for root_handler in logging.root.handlers:
        if not isinstance(root_handler, logging.StreamHandler):
            continue
        if root_handler.stream is not None:
            continue
        root_handler.stream = sys.stderr

def add_logging_handler(logger: logging.Logger, handler: logging.Handler):
    handler_class_name = handler.__class__.__name__
    logging._acquireLock() # type: ignore
    try:
        handlers = logger.handlers
        found_handler = False
        for handler_i in range(len(handlers)-1, -1, -1):
            existing_handler = handlers[handler_i]
            if existing_handler.__class__.__name__ != handler_class_name:
                continue
            existing_handler.flush()
            existing_handler.close()
            if not found_handler:
                handlers[handler_i] = handler
                found_handler = True
            else:
                del handlers[handler_i]
        if found_handler:
            return
    finally:
        logging._releaseLock() # type: ignore

    logger.addHandler(handler)

def setup_logger(logger_name):
    setup_root_logger()

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if sys.stderr is not None:
        console_handler = StreamHandler(sys.stderr)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        add_logging_handler(logger, console_handler)

    qgis_handler = QgsLogHandler()
    qgis_formatter = logging.Formatter('%(levelname)s - %(message)s')
    qgis_handler.setFormatter(qgis_formatter)
    add_logging_handler(logger, qgis_handler)

    return logger

LOGGER = logging.getLogger(PLUGIN_NAME)

