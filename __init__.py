from .src.plugin import PKKToolsPlugin
from qgis.gui import QgisInterface
import qgis.utils


def classFactory(iface: QgisInterface):
    return PKKToolsPlugin(iface)

