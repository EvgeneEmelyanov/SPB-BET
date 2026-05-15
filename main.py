import sys
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QAction, QDrag
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
    QWidget,
    QVBoxLayout,
    QLabel,
    QFileDialog,
    QMessageBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)


@dataclass
class GsdmlCategory:
    category_id: str = ""
    text_id: str = ""
    name: str = ""


@dataclass
class GsdmlGraphic:
    graphic_id: str = ""
    graphic_file: str = ""
    resolved_file_path: str = ""
    file_exists: bool = False
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class GsdmlIoDataItem:
    direction: str = ""
    data_type: str = ""
    text_id: str = ""
    name: str = ""
    bit_length: str = ""
    use_as_bits: str = ""
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class GsdmlSubmodule:
    submodule_id: str = ""
    name: str = ""
    text_id: str = ""
    info_text: str = ""
    submodule_ident_number: str = ""
    kind: str = ""

    input_items: list[GsdmlIoDataItem] = field(default_factory=list)
    output_items: list[GsdmlIoDataItem] = field(default_factory=list)

    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class GsdmlModule:
    module_id: str = ""
    name: str = ""
    text_id: str = ""
    info_text: str = ""
    module_ident_number: str = ""
    order_number: str = ""
    kind: str = "ModuleItem"

    category_ref: str = ""
    category_name: str = ""
    subcategory_ref: str = ""
    subcategory_name: str = ""

    submodules: list[GsdmlSubmodule] = field(default_factory=list)

    attributes: dict[str, str] = field(default_factory=dict)

@dataclass
class GsdmlModuleRef:
    module_item_target: str = ""
    fixed_in_slots: str = ""
    used_in_slots: str = ""
    allowed_in_slots: str = ""
    module: GsdmlModule | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class GsdmlDeviceAccessPoint:
    dap_id: str = ""
    name: str = ""
    display_name: str = ""
    text_id: str = ""

    module_ident_number: str = ""
    fixed_in_slots: str = ""
    physical_slots: str = ""
    dns_compatible_name: str = ""
    order_number: str = ""
    hardware_release: str = ""
    software_release: str = ""
    info_text: str = ""

    category_ref: str = ""
    category_name: str = ""
    subcategory_ref: str = ""
    subcategory_name: str = ""

    graphics_ref: str = ""

    submodules: list[GsdmlSubmodule] = field(default_factory=list)
    module_refs: list[GsdmlModuleRef] = field(default_factory=list)

    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class GsdmlDevice:
    vendor_id: str = ""
    device_id: str = ""
    vendor_name: str = ""
    device_name: str = ""
    info_text: str = ""
    family: str = ""

    texts: dict[str, str] = field(default_factory=dict)
    categories: dict[str, GsdmlCategory] = field(default_factory=dict)
    graphics: list[GsdmlGraphic] = field(default_factory=list)

    device_access_points: list[GsdmlDeviceAccessPoint] = field(default_factory=list)
    modules: list[GsdmlModule] = field(default_factory=list)


@dataclass
class ProjectGsdFile:
    file_path: str
    file_name: str
    file_extension: str

    is_xml: bool = False
    root_tag: str = ""
    gsdml_version: str = ""

    has_profile_header: bool = False
    has_profile_body: bool = False
    has_device_identity: bool = False

    device: GsdmlDevice = field(default_factory=GsdmlDevice)

    @property
    def vendor_name(self) -> str:
        return self.device.vendor_name

    @property
    def device_name(self) -> str:
        return self.device.device_name


@dataclass
class ProjectDeviceInstance:
    instance_name: str
    source_gsd_file_index: int
    gsd_file: ProjectGsdFile
    selected_dap: GsdmlDeviceAccessPoint


class GsdmlReader:
    @staticmethod
    def read(file_path: str) -> ProjectGsdFile:
        path = Path(file_path)

        gsd_file = ProjectGsdFile(
            file_path=str(path),
            file_name=path.name,
            file_extension=path.suffix.lower(),
        )

        tree = ET.parse(path)
        root = tree.getroot()

        gsd_file.is_xml = True
        gsd_file.root_tag = GsdmlReader.local_name(root.tag)
        gsd_file.gsdml_version = GsdmlReader.read_gsdml_version(root)

        profile_header = GsdmlReader.find_first(root, "ProfileHeader")
        profile_body = GsdmlReader.find_first(root, "ProfileBody")
        device_identity = GsdmlReader.find_first(root, "DeviceIdentity")

        gsd_file.has_profile_header = profile_header is not None
        gsd_file.has_profile_body = profile_body is not None
        gsd_file.has_device_identity = device_identity is not None

        device = GsdmlDevice()

        device.texts = GsdmlReader.read_external_texts(root)
        device.categories = GsdmlReader.read_category_list(root, device.texts)
        device.graphics = GsdmlReader.read_graphics_list(root, path)

        GsdmlReader.read_device_identity(root, device)
        GsdmlReader.read_device_function(root, device)

        device.modules = GsdmlReader.read_modules(root, device.texts, device.categories)

        modules_by_id = {
            module.module_id: module
            for module in device.modules
            if module.module_id
        }

        device.device_access_points = GsdmlReader.read_device_access_points(
            root,
            device.texts,
            device.categories,
            modules_by_id,
        )

        if not device.device_name:
            device.device_name = path.stem

        gsd_file.device = device

        return gsd_file

    @staticmethod
    def local_name(tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    @staticmethod
    def find_first(root: ET.Element, local_tag_name: str):
        for element in root.iter():
            if GsdmlReader.local_name(element.tag) == local_tag_name:
                return element
        return None

    @staticmethod
    def find_first_inside(parent: ET.Element, local_tag_name: str):
        for element in parent.iter():
            if GsdmlReader.local_name(element.tag) == local_tag_name:
                return element
        return None

    @staticmethod
    def iter_by_local_name(root: ET.Element, local_tag_name: str):
        for element in root.iter():
            if GsdmlReader.local_name(element.tag) == local_tag_name:
                yield element

    @staticmethod
    def get_attr_any(element: ET.Element | None, attr_names: list[str]) -> str:
        if element is None:
            return ""

        for attr_name in attr_names:
            if attr_name in element.attrib:
                return element.attrib[attr_name]

        return ""

    @staticmethod
    def read_gsdml_version(root: ET.Element) -> str:
        version = (
            root.attrib.get("Version", "")
            or root.attrib.get("SchemaVersion", "")
            or root.attrib.get("ProfileRevision", "")
        )

        if version:
            return version

        profile_header = GsdmlReader.find_first(root, "ProfileHeader")

        if profile_header is not None:
            return (
                profile_header.attrib.get("Version", "")
                or profile_header.attrib.get("ProfileRevision", "")
                or profile_header.attrib.get("SchemaVersion", "")
            )

        return ""

    @staticmethod
    def read_external_texts(root: ET.Element) -> dict[str, str]:
        texts: dict[str, str] = {}

        for element in root.iter():
            if GsdmlReader.local_name(element.tag) != "Text":
                continue

            text_id = element.attrib.get("TextId", "")
            value = element.attrib.get("Value", "")

            if text_id and value:
                texts[text_id] = value

        return texts

    @staticmethod
    def read_category_list(
        root: ET.Element,
        texts: dict[str, str],
    ) -> dict[str, GsdmlCategory]:
        categories: dict[str, GsdmlCategory] = {}

        for element in GsdmlReader.iter_by_local_name(root, "CategoryItem"):
            category_id = element.attrib.get("ID", "")
            text_id = element.attrib.get("TextId", "")
            name = GsdmlReader.resolve_text(texts, text_id)

            if category_id:
                categories[category_id] = GsdmlCategory(
                    category_id=category_id,
                    text_id=text_id,
                    name=name,
                )

        return categories

    @staticmethod
    def resolve_text(texts: dict[str, str], text_id: str) -> str:
        if not text_id:
            return ""

        return texts.get(text_id, text_id)

    @staticmethod
    def resolve_category_name(
        categories: dict[str, GsdmlCategory],
        category_ref: str,
    ) -> str:
        if not category_ref:
            return ""

        category = categories.get(category_ref)

        if category is None:
            return category_ref

        return category.name or category.category_id

    @staticmethod
    def read_graphics_list(root: ET.Element, gsdml_file_path: Path) -> list[GsdmlGraphic]:
        graphics: list[GsdmlGraphic] = []

        base_dir = gsdml_file_path.parent
        possible_extensions = ["", ".bmp", ".png", ".jpg", ".jpeg", ".gif"]

        for element in GsdmlReader.iter_by_local_name(root, "GraphicItem"):
            graphic_id = element.attrib.get("ID", "")
            graphic_file = element.attrib.get("GraphicFile", "")

            resolved_file_path = ""
            file_exists = False

            if graphic_file:
                for extension in possible_extensions:
                    candidate = base_dir / f"{graphic_file}{extension}"

                    if candidate.exists():
                        resolved_file_path = str(candidate)
                        file_exists = True
                        break

            graphics.append(
                GsdmlGraphic(
                    graphic_id=graphic_id,
                    graphic_file=graphic_file,
                    resolved_file_path=resolved_file_path,
                    file_exists=file_exists,
                    attributes=dict(element.attrib),
                )
            )

        return graphics

    @staticmethod
    def read_device_identity(root: ET.Element, device: GsdmlDevice):
        device_identity = GsdmlReader.find_first(root, "DeviceIdentity")

        if device_identity is None:
            return

        device.vendor_id = GsdmlReader.get_attr_any(
            device_identity,
            ["VendorID", "VendorId", "Vendor_ID"]
        )

        device.device_id = GsdmlReader.get_attr_any(
            device_identity,
            ["DeviceID", "DeviceId", "Device_ID"]
        )

        vendor_name_element = GsdmlReader.find_first_inside(device_identity, "VendorName")
        info_text_element = GsdmlReader.find_first_inside(device_identity, "InfoText")

        if vendor_name_element is not None:
            device.vendor_name = (
                vendor_name_element.attrib.get("Value", "")
                or GsdmlReader.resolve_text(
                    device.texts,
                    vendor_name_element.attrib.get("TextId", "")
                )
            )

        if info_text_element is not None:
            text_id = info_text_element.attrib.get("TextId", "")
            device.info_text = GsdmlReader.resolve_text(device.texts, text_id)
            device.device_name = device.info_text

        if not device.vendor_name:
            device.vendor_name = GsdmlReader.find_text_or_attr(
                root,
                ["VendorName", "Vendor_Name", "Manufacturer"]
            )

        if not device.device_name:
            device.device_name = GsdmlReader.find_text_or_attr(
                root,
                ["DeviceName", "Device_Name", "InfoText", "NameOfStation"]
            )

    @staticmethod
    def read_device_function(root: ET.Element, device: GsdmlDevice):
        family_element = GsdmlReader.find_first(root, "Family")

        if family_element is None:
            return

        device.family = (
            family_element.attrib.get("Value", "")
            or GsdmlReader.resolve_text(
                device.texts,
                family_element.attrib.get("TextId", "")
            )
            or (family_element.text.strip() if family_element.text else "")
        )

    @staticmethod
    def read_modules(
        root: ET.Element,
        texts: dict[str, str],
        categories: dict[str, GsdmlCategory],
    ) -> list[GsdmlModule]:
        result: list[GsdmlModule] = []

        for module_element in GsdmlReader.iter_by_local_name(root, "ModuleItem"):
            module_info = GsdmlReader.read_module_info(module_element, texts, categories)

            module = GsdmlModule(
                module_id=module_element.attrib.get("ID", ""),
                name=module_info["name"],
                text_id=module_info["text_id"],
                info_text=module_info["info_text"],
                module_ident_number=module_element.attrib.get("ModuleIdentNumber", ""),
                order_number=module_info["order_number"],
                kind="ModuleItem",
                category_ref=module_info["category_ref"],
                category_name=module_info["category_name"],
                subcategory_ref=module_info["subcategory_ref"],
                subcategory_name=module_info["subcategory_name"],
                attributes=dict(module_element.attrib),
            )

            module.submodules = GsdmlReader.read_submodules_inside(module_element, texts)

            result.append(module)

        return result

    @staticmethod
    def read_device_access_points(
        root: ET.Element,
        texts: dict[str, str],
        categories: dict[str, GsdmlCategory],
        modules_by_id: dict[str, GsdmlModule],
    ) -> list[GsdmlDeviceAccessPoint]:
        result: list[GsdmlDeviceAccessPoint] = []

        for dap_element in GsdmlReader.iter_by_local_name(root, "DeviceAccessPointItem"):
            module_info = GsdmlReader.read_module_info(dap_element, texts, categories)

            dap = GsdmlDeviceAccessPoint(
                dap_id=dap_element.attrib.get("ID", ""),
                name=module_info["name"],
                text_id=module_info["text_id"],
                module_ident_number=dap_element.attrib.get("ModuleIdentNumber", ""),
                fixed_in_slots=dap_element.attrib.get("FixedInSlots", ""),
                physical_slots=dap_element.attrib.get("PhysicalSlots", ""),
                dns_compatible_name=dap_element.attrib.get("DNS_CompatibleName", ""),
                order_number=module_info["order_number"],
                hardware_release=module_info["hardware_release"],
                software_release=module_info["software_release"],
                info_text=module_info["info_text"],
                category_ref=module_info["category_ref"],
                category_name=module_info["category_name"],
                subcategory_ref=module_info["subcategory_ref"],
                subcategory_name=module_info["subcategory_name"],
                graphics_ref=GsdmlReader.read_graphics_ref(dap_element),
                attributes=dict(dap_element.attrib),
            )

            dap.display_name = GsdmlReader.make_dap_display_name(dap)

            dap.submodules = GsdmlReader.read_submodules_inside(dap_element, texts)
            dap.module_refs = GsdmlReader.read_useable_modules(dap_element, modules_by_id)

            result.append(dap)

        return result

    @staticmethod
    def make_dap_display_name(dap: GsdmlDeviceAccessPoint) -> str:
        base_name = (
            dap.category_name
            or dap.dns_compatible_name
            or dap.name
            or dap.dap_id
        )

        parts = [base_name]

        if dap.software_release:
            parts.append(dap.software_release)

        if dap.order_number:
            parts.append(dap.order_number)

        return " / ".join(part for part in parts if part)

    @staticmethod
    def read_useable_modules(
        dap_element: ET.Element,
        modules_by_id: dict[str, GsdmlModule],
    ) -> list[GsdmlModuleRef]:
        result: list[GsdmlModuleRef] = []

        useable_modules_element = GsdmlReader.find_first_inside(dap_element, "UseableModules")

        if useable_modules_element is None:
            return result

        for ref_element in useable_modules_element:
            if GsdmlReader.local_name(ref_element.tag) != "ModuleItemRef":
                continue

            module_target = ref_element.attrib.get("ModuleItemTarget", "")

            module_ref = GsdmlModuleRef(
                module_item_target=module_target,
                fixed_in_slots=ref_element.attrib.get("FixedInSlots", ""),
                used_in_slots=ref_element.attrib.get("UsedInSlots", ""),
                allowed_in_slots=ref_element.attrib.get("AllowedInSlots", ""),
                module=modules_by_id.get(module_target),
                attributes=dict(ref_element.attrib),
            )

            result.append(module_ref)

        return result

    @staticmethod
    def read_submodules_inside(
        parent: ET.Element,
        texts: dict[str, str],
    ) -> list[GsdmlSubmodule]:
        result: list[GsdmlSubmodule] = []

        for element in parent.iter():
            local_tag = GsdmlReader.local_name(element.tag)

            if local_tag not in ["SubmoduleItem", "VirtualSubmoduleItem"]:
                continue

            module_info = GsdmlReader.read_module_info(element, texts, {})

            submodule = GsdmlSubmodule(
                submodule_id=element.attrib.get("ID", ""),
                name=module_info["name"],
                text_id=module_info["text_id"],
                info_text=module_info["info_text"],
                submodule_ident_number=element.attrib.get("SubmoduleIdentNumber", ""),
                kind=local_tag,
                attributes=dict(element.attrib),
            )

            input_items, output_items = GsdmlReader.read_io_data(element, texts)

            submodule.input_items = input_items
            submodule.output_items = output_items

            result.append(submodule)

        return result

    @staticmethod
    def read_module_info(
        element: ET.Element,
        texts: dict[str, str],
        categories: dict[str, GsdmlCategory],
    ) -> dict[str, str]:
        result = {
            "name": "",
            "text_id": "",
            "info_text": "",
            "order_number": "",
            "hardware_release": "",
            "software_release": "",
            "category_ref": "",
            "category_name": "",
            "subcategory_ref": "",
            "subcategory_name": "",
        }

        module_info = GsdmlReader.find_first_inside(element, "ModuleInfo")

        if module_info is None:
            return result

        category_ref = module_info.attrib.get("CategoryRef", "")
        subcategory_ref = module_info.attrib.get("SubCategory1Ref", "")

        result["category_ref"] = category_ref
        result["subcategory_ref"] = subcategory_ref
        result["category_name"] = GsdmlReader.resolve_category_name(categories, category_ref)
        result["subcategory_name"] = GsdmlReader.resolve_category_name(categories, subcategory_ref)

        name_element = GsdmlReader.find_first_inside(module_info, "Name")
        info_text_element = GsdmlReader.find_first_inside(module_info, "InfoText")
        order_number_element = GsdmlReader.find_first_inside(module_info, "OrderNumber")
        hardware_release_element = GsdmlReader.find_first_inside(module_info, "HardwareRelease")
        software_release_element = GsdmlReader.find_first_inside(module_info, "SoftwareRelease")

        if name_element is not None:
            text_id = name_element.attrib.get("TextId", "")

            result["text_id"] = text_id
            result["name"] = (
                name_element.attrib.get("Value", "")
                or GsdmlReader.resolve_text(texts, text_id)
            )

        if info_text_element is not None:
            text_id = info_text_element.attrib.get("TextId", "")

            result["info_text"] = (
                info_text_element.attrib.get("Value", "")
                or GsdmlReader.resolve_text(texts, text_id)
            )

        if order_number_element is not None:
            result["order_number"] = (
                order_number_element.attrib.get("Value", "")
                or (order_number_element.text.strip() if order_number_element.text else "")
            )

        if hardware_release_element is not None:
            result["hardware_release"] = (
                hardware_release_element.attrib.get("Value", "")
                or (hardware_release_element.text.strip() if hardware_release_element.text else "")
            )

        if software_release_element is not None:
            result["software_release"] = (
                software_release_element.attrib.get("Value", "")
                or (software_release_element.text.strip() if software_release_element.text else "")
            )

        return result

    @staticmethod
    def read_graphics_ref(element: ET.Element) -> str:
        direct_ref = (
            element.attrib.get("GraphicItemRef", "")
            or element.attrib.get("GraphicsItemRef", "")
            or element.attrib.get("GraphicRef", "")
        )

        if direct_ref:
            return direct_ref

        graphics_element = GsdmlReader.find_first_inside(element, "Graphics")

        if graphics_element is not None:
            graphic_ref = graphics_element.attrib.get("GraphicItemTarget", "")

            if graphic_ref:
                return graphic_ref

        return ""

    @staticmethod
    def read_io_data(
        submodule_element: ET.Element,
        texts: dict[str, str],
    ) -> tuple[list[GsdmlIoDataItem], list[GsdmlIoDataItem]]:
        input_items: list[GsdmlIoDataItem] = []
        output_items: list[GsdmlIoDataItem] = []

        for io_data_element in submodule_element.iter():
            if GsdmlReader.local_name(io_data_element.tag) != "IOData":
                continue

            for direction_element in list(io_data_element):
                direction = GsdmlReader.local_name(direction_element.tag)

                if direction not in ["Input", "Output"]:
                    continue

                for data_item_element in direction_element.iter():
                    if GsdmlReader.local_name(data_item_element.tag) != "DataItem":
                        continue

                    text_id = data_item_element.attrib.get("TextId", "")

                    item = GsdmlIoDataItem(
                        direction=direction,
                        data_type=data_item_element.attrib.get("DataType", ""),
                        text_id=text_id,
                        name=GsdmlReader.resolve_text(texts, text_id),
                        bit_length=data_item_element.attrib.get("BitLength", ""),
                        use_as_bits=data_item_element.attrib.get("UseAsBits", ""),
                        attributes=dict(data_item_element.attrib),
                    )

                    if direction == "Input":
                        input_items.append(item)
                    else:
                        output_items.append(item)

        return input_items, output_items

    @staticmethod
    def find_text_or_attr(root: ET.Element, names: list[str]) -> str:
        for element in root.iter():
            local_tag = GsdmlReader.local_name(element.tag)

            if local_tag in names:
                if element.text and element.text.strip():
                    return element.text.strip()

                for value in element.attrib.values():
                    if value.strip():
                        return value.strip()

            for attr_name, attr_value in element.attrib.items():
                if attr_name in names and attr_value.strip():
                    return attr_value.strip()

        return ""


@dataclass
class SbpBetProject:
    project_name: str = "Новый проект"
    loaded_gsd_files: list[ProjectGsdFile] = field(default_factory=list)
    device_instances: list[ProjectDeviceInstance] = field(default_factory=list)

    def add_gsd_file(self, file_path: str) -> ProjectGsdFile:
        gsd_file = GsdmlReader.read(file_path)
        self.loaded_gsd_files.append(gsd_file)
        return gsd_file

    def contains_gsd_file(self, file_path: str) -> bool:
        new_path = Path(file_path).resolve()

        for gsd_file in self.loaded_gsd_files:
            existing_path = Path(gsd_file.file_path).resolve()

            if existing_path == new_path:
                return True

        return False

    def add_device_instance(
        self,
        source_gsd_file_index: int,
        selected_dap: GsdmlDeviceAccessPoint,
    ) -> ProjectDeviceInstance:
        gsd_file = self.loaded_gsd_files[source_gsd_file_index]

        base_name = (
            selected_dap.category_name
            or selected_dap.dns_compatible_name
            or selected_dap.name
            or gsd_file.device.device_name
            or gsd_file.file_name
        )

        instance_number = len(self.device_instances) + 1

        instance = ProjectDeviceInstance(
            instance_name=f"{base_name}_{instance_number}",
            source_gsd_file_index=source_gsd_file_index,
            gsd_file=gsd_file,
            selected_dap=selected_dap,
        )

        self.device_instances.append(instance)

        return instance


class HardwareCatalogTree(QTreeWidget):
    MIME_TYPE = "application/x-sbp-bet-hardware-catalog-item"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setHeaderLabels(["Hardware Catalog"])
        self.setDragEnabled(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)

    def startDrag(self, supported_actions):
        item = self.currentItem()

        if item is None:
            return

        payload = item.data(0, Qt.UserRole)

        if not isinstance(payload, dict):
            return

        # Перетаскиваем только DAP.
        # ModuleItem пока остаётся справочной частью каталога.
        if payload.get("type") != "dap":
            return

        mime = QMimeData()
        mime.setData(
            self.MIME_TYPE,
            json.dumps(payload).encode("utf-8"),
        )
        mime.setText(item.text(0))

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class ProjectTree(QTreeWidget):
    def __init__(self, drop_callback, parent=None):
        super().__init__(parent)

        self.drop_callback = drop_callback

        self.setHeaderLabels(["Дерево проекта"])
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DropOnly)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(HardwareCatalogTree.MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(HardwareCatalogTree.MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(HardwareCatalogTree.MIME_TYPE):
            event.ignore()
            return

        raw_payload = bytes(
            event.mimeData().data(HardwareCatalogTree.MIME_TYPE)
        ).decode("utf-8")

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            event.ignore()
            return

        success = self.drop_callback(payload)

        if success:
            event.acceptProposedAction()
        else:
            event.ignore()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.project = SbpBetProject()

        self.setWindowTitle("SBP-BET")
        self.resize(1400, 800)

        self.create_menu()
        self.create_main_layout()

    def create_menu(self):
        menu_bar = self.menuBar()

        project_menu = menu_bar.addMenu("Проект")

        load_gsd_action = QAction("Загрузить GSDML/XML", self)
        load_gsd_action.triggered.connect(self.on_load_gsd_clicked)
        project_menu.addAction(load_gsd_action)

        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        project_menu.addAction(exit_action)

    def create_main_layout(self):
        main_splitter = QSplitter(Qt.Horizontal)

        self.project_tree = ProjectTree(self.on_hardware_item_dropped_to_project)
        self.project_tree.itemClicked.connect(self.on_project_tree_item_clicked)

        root_item = QTreeWidgetItem(["Проект SBP-BET"])
        self.project_tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)

        self.center_tabs = QTabWidget()

        self.overview_text_area = QTextEdit()
        self.overview_text_area.setReadOnly(True)

        self.io_data_table = QTableWidget()
        self.io_data_table.setColumnCount(8)
        self.io_data_table.setHorizontalHeaderLabels(
            [
                "Direction",
                "Submodule",
                "Name",
                "DataType",
                "BitLength",
                "UseAsBits",
                "TextId",
                "Attributes",
            ]
        )
        self.io_data_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.io_data_table.horizontalHeader().setStretchLastSection(True)

        self.raw_text_area = QTextEdit()
        self.raw_text_area.setReadOnly(True)

        self.center_tabs.addTab(self.overview_text_area, "Обзор")
        self.center_tabs.addTab(self.io_data_table, "IO Data")
        self.center_tabs.addTab(self.raw_text_area, "Raw")

        self.set_overview_text(
            "SBP-BET\n\n"
            "1. Загрузите GSDML/XML через меню Проект.\n"
            "2. Справа появится дерево Hardware Catalog.\n"
            "3. Перетащите конкретный DAP справа налево, чтобы добавить устройство в проект.\n"
            "4. ModuleItem справа пока используется как справочная информация."
        )

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_title = QLabel("Загруженные GSDML/XML")
        self.hardware_catalog = HardwareCatalogTree()
        self.hardware_catalog.itemClicked.connect(self.on_hardware_catalog_item_clicked)

        right_layout.addWidget(right_title)
        right_layout.addWidget(self.hardware_catalog)

        main_splitter.addWidget(self.project_tree)
        main_splitter.addWidget(self.center_tabs)
        main_splitter.addWidget(right_panel)

        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 5)
        main_splitter.setStretchFactor(2, 2)

        self.setCentralWidget(main_splitter)

    def set_overview_text(self, text: str):
        self.overview_text_area.setText(text)
        self.center_tabs.setCurrentWidget(self.overview_text_area)

    def set_raw_data(self, data):
        self.raw_text_area.setText(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=4,
            )
        )

    def clear_io_table(self):
        self.io_data_table.setRowCount(0)

    def fill_io_table_from_submodules(self, submodules: list[GsdmlSubmodule]):
        rows = []

        for submodule in submodules:
            for item in submodule.input_items:
                rows.append((submodule, item))

            for item in submodule.output_items:
                rows.append((submodule, item))

        self.io_data_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            submodule, item = row

            values = [
                item.direction,
                submodule.name or submodule.submodule_id,
                item.name,
                item.data_type,
                item.bit_length,
                item.use_as_bits,
                item.text_id,
                json.dumps(item.attributes, ensure_ascii=False),
            ]

            for column_index, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))
                table_item.setFlags(table_item.flags() ^ Qt.ItemIsEditable)
                self.io_data_table.setItem(row_index, column_index, table_item)

        self.io_data_table.resizeColumnsToContents()

    def fill_io_table_from_dap(self, dap: GsdmlDeviceAccessPoint):
        submodules = list(dap.submodules)

        for module_ref in dap.module_refs:
            if module_ref.module is not None:
                submodules.extend(module_ref.module.submodules)

        self.fill_io_table_from_submodules(submodules)

    def on_load_gsd_clicked(self):
        file_path, selected_filter = QFileDialog.getOpenFileName(
            self,
            "Загрузить GSDML/XML файл",
            "",
            "GSDML/XML files (*.gsdml *.xml);;All files (*.*)"
        )

        if not file_path:
            return

        if self.project.contains_gsd_file(file_path):
            QMessageBox.information(
                self,
                "Файл уже добавлен",
                "Этот GSDML/XML файл уже добавлен в проект."
            )
            return

        try:
            gsd_file = self.project.add_gsd_file(file_path)
        except ET.ParseError as error:
            self.set_overview_text(
                "Ошибка чтения XML-файла.\n\n"
                f"Файл: {file_path}\n\n"
                f"Ошибка XML:\n{error}"
            )
            self.clear_io_table()
            self.set_raw_data({})
            return
        except Exception as error:
            self.set_overview_text(
                "Не удалось загрузить GSDML/XML файл.\n\n"
                f"Файл: {file_path}\n\n"
                f"Ошибка:\n{error}"
            )
            self.clear_io_table()
            self.set_raw_data({})
            return

        file_index = len(self.project.loaded_gsd_files) - 1
        self.add_gsd_file_to_hardware_catalog(file_index, gsd_file)
        self.show_gsd_file_info(gsd_file)

    def add_gsd_file_to_hardware_catalog(self, file_index: int, gsd_file: ProjectGsdFile):
        """
        Добавляет GSDML-файл в правый Hardware Catalog.

        Справа показываем только варианты устройства / DAP.
        ModuleItem не показываем отдельным деревом, потому что это состав выбранного DAP,
        а не самостоятельные устройства для добавления в проект.
        """

        device = gsd_file.device

        title = device.device_name or gsd_file.file_name

        if device.vendor_name:
            title = f"{device.vendor_name} — {title}"

        file_item = QTreeWidgetItem([title])
        file_item.setData(
            0,
            Qt.UserRole,
            {
                "type": "file",
                "file_index": file_index,
            },
        )

        dap_root_item = QTreeWidgetItem(["Варианты устройства / DAP"])

        for dap_index, dap in enumerate(device.device_access_points):
            dap_title = dap.display_name or dap.dns_compatible_name or dap.name or dap.dap_id

            dap_item = QTreeWidgetItem([dap_title])
            dap_item.setData(
                0,
                Qt.UserRole,
                {
                    "type": "dap",
                    "file_index": file_index,
                    "dap_index": dap_index,
                },
            )

            dap_item.addChild(QTreeWidgetItem([f"ID: {dap.dap_id or '-'}"]))
            dap_item.addChild(QTreeWidgetItem([f"DNS name: {dap.dns_compatible_name or '-'}"]))
            dap_item.addChild(QTreeWidgetItem([f"Category: {dap.category_name or '-'}"]))
            dap_item.addChild(QTreeWidgetItem([f"OrderNumber: {dap.order_number or '-'}"]))
            dap_item.addChild(QTreeWidgetItem([f"SoftwareRelease: {dap.software_release or '-'}"]))
            dap_item.addChild(QTreeWidgetItem([f"PhysicalSlots: {dap.physical_slots or '-'}"]))
            dap_item.addChild(QTreeWidgetItem([f"UseableModules: {len(dap.module_refs)}"]))

            dap_root_item.addChild(dap_item)

        file_item.addChild(dap_root_item)

        self.hardware_catalog.addTopLevelItem(file_item)

        file_item.setExpanded(True)
        dap_root_item.setExpanded(True)

    def on_hardware_item_dropped_to_project(self, payload: dict) -> bool:
        item_type = payload.get("type")
        file_index = payload.get("file_index")

        if item_type != "dap":
            return False

        if file_index is None:
            return False

        if file_index < 0 or file_index >= len(self.project.loaded_gsd_files):
            return False

        dap_index = payload.get("dap_index")

        if dap_index is None:
            return False

        return self.add_dap_to_project(file_index, dap_index)

    def add_dap_to_project(self, file_index: int, dap_index: int) -> bool:
        gsd_file = self.project.loaded_gsd_files[file_index]
        device = gsd_file.device

        if dap_index < 0 or dap_index >= len(device.device_access_points):
            return False

        selected_dap = device.device_access_points[dap_index]

        instance = self.project.add_device_instance(file_index, selected_dap)

        self.add_device_instance_to_project_tree(instance)
        self.show_project_device_instance_info(instance)

        return True

    def add_device_instance_to_project_tree(self, instance: ProjectDeviceInstance):
        root_item = self.project_tree.topLevelItem(0)

        device = instance.gsd_file.device
        dap = instance.selected_dap

        device_title = instance.instance_name

        if device.vendor_name:
            device_title = f"{device.vendor_name} — {device_title}"

        device_item = QTreeWidgetItem([device_title])
        device_item.setData(0, Qt.UserRole, instance)

        dap_item = QTreeWidgetItem(
            [f"Slot 0: DAP {dap.display_name or dap.dns_compatible_name or dap.name or dap.dap_id or '-'}"]
        )
        dap_item.setData(0, Qt.UserRole, dap)

        slots_root_item = QTreeWidgetItem(["Слоты устройства"])
        slots_root_item.setData(0, Qt.UserRole, {"type": "slots_root", "instance": instance})

        for module_ref in dap.module_refs:
            module = module_ref.module

            if module is None:
                module_name = module_ref.module_item_target
            else:
                module_name = module.name or module.category_name or module.module_id

            if module_ref.fixed_in_slots:
                slot_text = f"FixedInSlots {module_ref.fixed_in_slots}: {module_name}"
                slot_kind = "fixed"
            elif module_ref.used_in_slots:
                slot_text = f"UsedInSlots {module_ref.used_in_slots}: {module_name}"
                slot_kind = "used"
            elif module_ref.allowed_in_slots:
                slot_text = f"AllowedInSlots {module_ref.allowed_in_slots}: {module_name}"
                slot_kind = "allowed"
            else:
                slot_text = f"ModuleRef: {module_name}"
                slot_kind = "unknown"

            slot_item = QTreeWidgetItem([slot_text])
            slot_item.setData(0, Qt.UserRole, module_ref)

            slot_item.addChild(QTreeWidgetItem([f"Тип: {slot_kind}"]))
            slot_item.addChild(QTreeWidgetItem([f"ModuleItemTarget: {module_ref.module_item_target or '-'}"]))

            if module is not None:
                slot_item.addChild(QTreeWidgetItem([f"ID: {module.module_id or '-'}"]))
                slot_item.addChild(QTreeWidgetItem([f"OrderNumber: {module.order_number or '-'}"]))
                slot_item.addChild(QTreeWidgetItem([f"Подмодулей: {len(module.submodules)}"]))

            slots_root_item.addChild(slot_item)

        device_item.addChild(dap_item)
        device_item.addChild(slots_root_item)

        root_item.addChild(device_item)

        root_item.setExpanded(True)
        device_item.setExpanded(True)
        dap_item.setExpanded(True)
        slots_root_item.setExpanded(True)

    def show_gsd_file_info(self, gsd_file: ProjectGsdFile):
        device = gsd_file.device

        self.clear_io_table()

        self.set_overview_text(
            "GSDML/XML файл:\n\n"
            f"Проект: {self.project.project_name}\n"
            f"Имя файла: {gsd_file.file_name}\n"
            f"Расширение: {gsd_file.file_extension}\n"
            f"Полный путь: {gsd_file.file_path}\n\n"

            f"XML: {gsd_file.is_xml}\n"
            f"Корневой тег: {gsd_file.root_tag}\n"
            f"GSDML version: {gsd_file.gsdml_version or '-'}\n\n"

            f"ProfileHeader найден: {gsd_file.has_profile_header}\n"
            f"ProfileBody найден: {gsd_file.has_profile_body}\n"
            f"DeviceIdentity найден: {gsd_file.has_device_identity}\n\n"

            f"VendorID: {device.vendor_id or '-'}\n"
            f"DeviceID: {device.device_id or '-'}\n"
            f"Производитель: {device.vendor_name or '-'}\n"
            f"Устройство: {device.device_name or '-'}\n"
            f"Семейство: {device.family or '-'}\n\n"

            f"ExternalTextList записей: {len(device.texts)}\n"
            f"CategoryList записей: {len(device.categories)}\n"
            f"GraphicsList записей: {len(device.graphics)}\n"
            f"DeviceAccessPointItem: {len(device.device_access_points)}\n"
            f"ModuleItem: {len(device.modules)}\n\n"

            f"{self.format_dap_list_info(device)}\n"

            f"Экземпляров устройств в проекте: {len(self.project.device_instances)}\n"
            f"Всего GSDML/XML файлов в проекте: {len(self.project.loaded_gsd_files)}"
        )

        self.set_raw_data(
            {
                "file": {
                    "file_path": gsd_file.file_path,
                    "file_name": gsd_file.file_name,
                    "file_extension": gsd_file.file_extension,
                    "root_tag": gsd_file.root_tag,
                    "gsdml_version": gsd_file.gsdml_version,
                },
                "device": {
                    "vendor_id": device.vendor_id,
                    "device_id": device.device_id,
                    "vendor_name": device.vendor_name,
                    "device_name": device.device_name,
                    "family": device.family,
                    "texts_count": len(device.texts),
                    "categories_count": len(device.categories),
                    "graphics_count": len(device.graphics),
                    "dap_count": len(device.device_access_points),
                    "modules_count": len(device.modules),
                },
            }
        )

    def show_project_device_instance_info(self, instance: ProjectDeviceInstance):
        device = instance.gsd_file.device
        dap = instance.selected_dap

        self.fill_io_table_from_dap(dap)

        self.set_overview_text(
            "Устройство в проекте:\n\n"
            f"Экземпляр: {instance.instance_name}\n"
            f"Производитель: {device.vendor_name or '-'}\n"
            f"Устройство из файла: {device.device_name or '-'}\n\n"

            f"Выбранный DAP / конкретное устройство:\n"
            f"  Название: {dap.display_name or '-'}\n"
            f"  Category: {dap.category_name or '-'}\n"
            f"  DNS name: {dap.dns_compatible_name or '-'}\n"
            f"  OrderNumber: {dap.order_number or '-'}\n"
            f"  SoftwareRelease: {dap.software_release or '-'}\n"
            f"  HardwareRelease: {dap.hardware_release or '-'}\n"
            f"  ID: {dap.dap_id or '-'}\n"
            f"  ModuleIdentNumber: {dap.module_ident_number or '-'}\n"
            f"  PhysicalSlots: {dap.physical_slots or '-'}\n"
            f"  FixedInSlots: {dap.fixed_in_slots or '-'}\n"
            f"  UseableModules: {len(dap.module_refs)}\n\n"

            f"{self.format_module_refs_info(dap)}"
        )

        self.set_raw_data(
            {
                "instance_name": instance.instance_name,
                "source_gsd_file_index": instance.source_gsd_file_index,
                "selected_dap": self.dap_to_dict(dap),
            }
        )

    def show_dap_info(self, dap: GsdmlDeviceAccessPoint):
        self.fill_io_table_from_dap(dap)

        self.set_overview_text(
            "DeviceAccessPointItem / конкретное устройство:\n\n"
            f"Название: {dap.display_name or '-'}\n"
            f"Category: {dap.category_name or '-'}\n"
            f"SubCategory: {dap.subcategory_name or '-'}\n"
            f"DNS name: {dap.dns_compatible_name or '-'}\n"
            f"OrderNumber: {dap.order_number or '-'}\n"
            f"SoftwareRelease: {dap.software_release or '-'}\n"
            f"HardwareRelease: {dap.hardware_release or '-'}\n"
            f"ID: {dap.dap_id or '-'}\n"
            f"ModuleIdentNumber: {dap.module_ident_number or '-'}\n"
            f"PhysicalSlots: {dap.physical_slots or '-'}\n"
            f"FixedInSlots: {dap.fixed_in_slots or '-'}\n"
            f"GraphicRef: {dap.graphics_ref or '-'}\n"
            f"Подмодулей DAP: {len(dap.submodules)}\n"
            f"UseableModules: {len(dap.module_refs)}\n\n"

            f"InfoText:\n{dap.info_text or '-'}\n\n"
            f"{self.format_module_refs_info(dap)}"
        )

        self.set_raw_data(self.dap_to_dict(dap))

    def show_module_info(self, module: GsdmlModule):
        input_count = 0
        output_count = 0

        for submodule in module.submodules:
            input_count += len(submodule.input_items)
            output_count += len(submodule.output_items)

        self.fill_io_table_from_submodules(module.submodules)

        self.set_overview_text(
            "ModuleItem / элемент состава устройства:\n\n"
            f"Название: {module.name or '-'}\n"
            f"Описание: {module.info_text or '-'}\n"
            f"Category: {module.category_name or '-'}\n"
            f"SubCategory: {module.subcategory_name or '-'}\n"
            f"ID: {module.module_id or '-'}\n"
            f"ModuleIdentNumber: {module.module_ident_number or '-'}\n"
            f"OrderNumber: {module.order_number or '-'}\n"
            f"Подмодулей: {len(module.submodules)}\n"
            f"Input DataItem: {input_count}\n"
            f"Output DataItem: {output_count}\n\n"
            "Этот ModuleItem не является самостоятельным устройством. "
            "Он используется внутри выбранного DAP через UseableModules."
        )

        self.set_raw_data(self.module_to_dict(module))

    def show_module_ref_info(self, module_ref: GsdmlModuleRef):
        module = module_ref.module

        if module is None:
            self.clear_io_table()
        else:
            self.fill_io_table_from_submodules(module.submodules)

        self.set_overview_text(
            "UseableModules / ModuleItemRef:\n\n"
            f"ModuleItemTarget: {module_ref.module_item_target or '-'}\n"
            f"FixedInSlots: {module_ref.fixed_in_slots or '-'}\n"
            f"UsedInSlots: {module_ref.used_in_slots or '-'}\n"
            f"AllowedInSlots: {module_ref.allowed_in_slots or '-'}\n\n"
            f"Связанный ModuleItem:\n"
            f"  Название: {(module.name if module else '') or '-'}\n"
            f"  ID: {(module.module_id if module else '') or '-'}\n"
            f"  OrderNumber: {(module.order_number if module else '') or '-'}\n\n"
            "FixedInSlots — модуль фиксирован в этих слотах.\n"
            "UsedInSlots — модуль уже используется в этих слотах.\n"
            "AllowedInSlots — допустимые слоты для выбора/установки."
        )

        self.set_raw_data(
            {
                "module_ref": module_ref.attributes,
                "module": self.module_to_dict(module) if module else None,
            }
        )

    def format_dap_list_info(self, device: GsdmlDevice) -> str:
        if not device.device_access_points:
            return "DAP не найдены.\n"

        lines = ["Доступные DAP / варианты устройства:"]

        for dap in device.device_access_points:
            lines.append(f"  - {dap.display_name or dap.dap_id or '-'}")
            lines.append(f"    ID: {dap.dap_id or '-'}")
            lines.append(f"    DNS name: {dap.dns_compatible_name or '-'}")
            lines.append(f"    PhysicalSlots: {dap.physical_slots or '-'}")
            lines.append(f"    UseableModules: {len(dap.module_refs)}")
            lines.append("")

        return "\n".join(lines)

    def format_module_refs_info(self, dap: GsdmlDeviceAccessPoint) -> str:
        if not dap.module_refs:
            return "UseableModules: не найдено."

        lines = ["UseableModules / состав выбранного устройства:"]

        for module_ref in dap.module_refs:
            module = module_ref.module
            module_name = module.name if module else module_ref.module_item_target

            lines.append(f"  Module: {module_name or '-'}")

            if module and module.info_text:
                lines.append(f"    Описание: {module.info_text}")

            if module and module.order_number:
                lines.append(f"    OrderNumber: {module.order_number}")

            if module and module.category_name:
                lines.append(f"    Category: {module.category_name}")

            if module_ref.fixed_in_slots:
                lines.append(f"    FixedInSlots: {module_ref.fixed_in_slots}")

            if module_ref.used_in_slots:
                lines.append(f"    UsedInSlots: {module_ref.used_in_slots}")

            if module_ref.allowed_in_slots:
                lines.append(f"    AllowedInSlots: {module_ref.allowed_in_slots}")

            lines.append("")

        return "\n".join(lines)

    def module_to_dict(self, module: GsdmlModule) -> dict:
        return {
            "module_id": module.module_id,
            "name": module.name,
            "text_id": module.text_id,
            "info_text": module.info_text,
            "module_ident_number": module.module_ident_number,
            "order_number": module.order_number,
            "category_ref": module.category_ref,
            "category_name": module.category_name,
            "subcategory_ref": module.subcategory_ref,
            "subcategory_name": module.subcategory_name,
            "attributes": module.attributes,
            "submodules": [
                {
                    "submodule_id": submodule.submodule_id,
                    "name": submodule.name,
                    "text_id": submodule.text_id,
                    "info_text": submodule.info_text,
                    "submodule_ident_number": submodule.submodule_ident_number,
                    "kind": submodule.kind,
                    "attributes": submodule.attributes,
                    "input_items": [item.attributes for item in submodule.input_items],
                    "output_items": [item.attributes for item in submodule.output_items],
                }
                for submodule in module.submodules
            ],
        }

    def dap_to_dict(self, dap: GsdmlDeviceAccessPoint) -> dict:
        return {
            "dap_id": dap.dap_id,
            "name": dap.name,
            "display_name": dap.display_name,
            "category_ref": dap.category_ref,
            "category_name": dap.category_name,
            "subcategory_ref": dap.subcategory_ref,
            "subcategory_name": dap.subcategory_name,
            "dns_compatible_name": dap.dns_compatible_name,
            "order_number": dap.order_number,
            "hardware_release": dap.hardware_release,
            "software_release": dap.software_release,
            "info_text": dap.info_text,
            "module_ident_number": dap.module_ident_number,
            "fixed_in_slots": dap.fixed_in_slots,
            "physical_slots": dap.physical_slots,
            "graphics_ref": dap.graphics_ref,
            "attributes": dap.attributes,
            "module_refs": [
                {
                    "module_item_target": ref.module_item_target,
                    "fixed_in_slots": ref.fixed_in_slots,
                    "used_in_slots": ref.used_in_slots,
                    "allowed_in_slots": ref.allowed_in_slots,
                    "module_name": ref.module.name if ref.module else "",
                    "module_order_number": ref.module.order_number if ref.module else "",
                    "attributes": ref.attributes,
                }
                for ref in dap.module_refs
            ],
        }

    def on_hardware_catalog_item_clicked(self, item: QTreeWidgetItem, column: int):
        payload = item.data(0, Qt.UserRole)

        if not isinstance(payload, dict):
            self.set_overview_text(item.text(0))
            self.clear_io_table()
            self.set_raw_data({})
            return

        item_type = payload.get("type")
        file_index = payload.get("file_index")

        if file_index is None:
            self.set_overview_text(item.text(0))
            self.clear_io_table()
            self.set_raw_data({})
            return

        if file_index < 0 or file_index >= len(self.project.loaded_gsd_files):
            return

        gsd_file = self.project.loaded_gsd_files[file_index]
        device = gsd_file.device

        if item_type == "file":
            self.show_gsd_file_info(gsd_file)
            return

        if item_type == "dap":
            dap_index = payload.get("dap_index")

            if dap_index is not None and 0 <= dap_index < len(device.device_access_points):
                self.show_dap_info(device.device_access_points[dap_index])
                return

        if item_type == "module":
            module_index = payload.get("module_index")

            if module_index is not None and 0 <= module_index < len(device.modules):
                self.show_module_info(device.modules[module_index])
                return

        self.set_overview_text(item.text(0))
        self.clear_io_table()
        self.set_raw_data({})

    def on_project_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        obj = item.data(0, Qt.UserRole)

        if isinstance(obj, ProjectDeviceInstance):
            self.show_project_device_instance_info(obj)
            return

        if isinstance(obj, GsdmlDeviceAccessPoint):
            self.show_dap_info(obj)
            return

        if isinstance(obj, GsdmlModuleRef):
            self.show_module_ref_info(obj)
            return

        self.set_overview_text(item.text(0))
        self.clear_io_table()
        self.set_raw_data({})


def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()