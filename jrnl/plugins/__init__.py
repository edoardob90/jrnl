# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

from typing import Type

from jrnl.plugins.calendar_heatmap_exporter import CalendarHeatmapExporter
from jrnl.plugins.dates_exporter import DatesExporter
from jrnl.plugins.dayone_json_importer import DayOneJSONImporter
from jrnl.plugins.fancy_exporter import FancyExporter
from jrnl.plugins.jrnl_importer import JRNLImporter
from jrnl.plugins.json_exporter import JSONExporter
from jrnl.plugins.markdown_exporter import MarkdownExporter
from jrnl.plugins.tag_exporter import TagExporter
from jrnl.plugins.text_exporter import TextExporter
from jrnl.plugins.xml_exporter import XMLExporter
from jrnl.plugins.yaml_exporter import YAMLExporter

__exporters = [
    CalendarHeatmapExporter,
    DatesExporter,
    FancyExporter,
    JSONExporter,
    MarkdownExporter,
    TagExporter,
    TextExporter,
    XMLExporter,
    YAMLExporter,
]
__importers = [JRNLImporter, DayOneJSONImporter]

__exporter_types = {name: plugin for plugin in __exporters for name in plugin.names}
__exporter_types["pretty"] = None
__exporter_types["short"] = None
__exporter_types["dayone"] = None
__importer_types = {name: plugin for plugin in __importers for name in plugin.names}

EXPORT_FORMATS = sorted(__exporter_types.keys())
IMPORT_FORMATS = sorted(__importer_types.keys())


def get_exporter(format: str) -> Type[TextExporter] | None:
    for exporter in __exporters:
        if hasattr(exporter, "names") and format in exporter.names:
            return exporter
    return None


def get_importer(format: str) -> Type[JRNLImporter] | None:
    for importer in __importers:
        if hasattr(importer, "names") and format in importer.names:
            return importer
    return None
