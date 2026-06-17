from PyQt5.QtWidgets import QWidget
import qgis.processing
from qgis.gui import QgsGui, QgsAbstractProcessingParameterWidgetWrapper
from qgis.core import Qgis, QgsProcessingParameterFeatureSink, QgsProcessingOutputLayerDefinition


class FeatureSinkWidgetWrapper:
    _parameter: QgsProcessingParameterFeatureSink
    _wrapper: QgsAbstractProcessingParameterWidgetWrapper
    _widget: QWidget

    def __init__(self, name: str, description: str, feature_type: Qgis.ProcessingSourceType):
        self._parameter = QgsProcessingParameterFeatureSink(
            name,
            description,
            feature_type)
        self._gui_registry = QgsGui.processingGuiRegistry()
        assert self._gui_registry is not None
        wrapper = self._gui_registry.createParameterWidgetWrapper(
            self._parameter,
            Qgis.ProcessingMode.Standard)
        assert wrapper is not None
        self._wrapper = wrapper
        self._processing_context = qgis.processing.createContext()
        widget = self._wrapper.createWrappedWidget(self._processing_context)
        assert widget is not None
        self._widget = widget

    def widget(self) -> QWidget:
        return self._widget
    
    def parameter_value(self) -> QgsProcessingOutputLayerDefinition:
        value = self._wrapper.parameterValue()
        assert isinstance(value, QgsProcessingOutputLayerDefinition)
        return value

