import sys
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
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QWidget,
    QVBoxLayout,
    QLabel,
    QFileDialog,
    QMessageBox,
    QInputDialog,
)


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
    module_ident_number: str = ""
    order_number: str = ""
    kind: str = "ModuleItem"

    submodules: list[GsdmlSubmodule] = field(default_factory=list)

    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class GsdmlDeviceAccessPoint:
    dap_id: str = ""
    name: str = ""
    text_id: str = ""
    module_ident_number: str = ""
    fixed_in_slots: str = ""
    graphics_ref: str = ""

    submodules: list[GsdmlSubmodule] = field(default_factory=list)

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
    def vendor_id(self) -> str:
        return self.device.vendor_id

    @property
    def device_id(self) -> str:
        return self.device.device_id

    @property
    def vendor_name(self) -> str:
        return self.device.vendor_name

    @property
    def device_name(self) -> str:
        return self.device.device_name

    @property
    def texts(self) -> dict[str, str]:
        return self.device.texts


@dataclass
class ProjectDeviceInstance:
    """
    Экземпляр устройства, добавленный в проект.

    Это уже не GSDML-файл в каталоге, а конкретное устройство
    внутри дерева проекта.
    """

    instance_name: str
    source_gsd_file_index: int
    gsd_file: ProjectGsdFile
    selected_dap: GsdmlDeviceAccessPoint

    assigned_modules: list[GsdmlModule] = field(default_factory=list)


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
        device.graphics = GsdmlReader.read_graphics_list(root, path)

        GsdmlReader.read_device_identity(root, device)
        GsdmlReader.read_device_function(root, device)

        device.device_access_points = GsdmlReader.read_device_access_points(root, device.texts)
        device.modules = GsdmlReader.read_modules(root, device.texts)

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
    def resolve_text(texts: dict[str, str], text_id: str) -> str:
        if not text_id:
            return ""

        return texts.get(text_id, text_id)

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
    def read_device_access_points(
        root: ET.Element,
        texts: dict[str, str],
    ) -> list[GsdmlDeviceAccessPoint]:
        result: list[GsdmlDeviceAccessPoint] = []

        for dap_element in GsdmlReader.iter_by_local_name(root, "DeviceAccessPointItem"):
            module_info = GsdmlReader.read_module_info(dap_element, texts)

            dap = GsdmlDeviceAccessPoint(
                dap_id=dap_element.attrib.get("ID", ""),
                name=module_info["name"],
                text_id=module_info["text_id"],
                module_ident_number=dap_element.attrib.get("ModuleIdentNumber", ""),
                fixed_in_slots=dap_element.attrib.get("FixedInSlots", ""),
                graphics_ref=GsdmlReader.read_graphics_ref(dap_element),
                attributes=dict(dap_element.attrib),
            )

            dap.submodules = GsdmlReader.read_submodules_inside(dap_element, texts)

            result.append(dap)

        return result

    @staticmethod
    def read_modules(
        root: ET.Element,
        texts: dict[str, str],
    ) -> list[GsdmlModule]:
        result: list[GsdmlModule] = []

        for module_element in GsdmlReader.iter_by_local_name(root, "ModuleItem"):
            module_info = GsdmlReader.read_module_info(module_element, texts)

            module = GsdmlModule(
                module_id=module_element.attrib.get("ID", ""),
                name=module_info["name"],
                text_id=module_info["text_id"],
                module_ident_number=module_element.attrib.get("ModuleIdentNumber", ""),
                order_number=module_info["order_number"],
                kind="ModuleItem",
                attributes=dict(module_element.attrib),
            )

            module.submodules = GsdmlReader.read_submodules_inside(module_element, texts)

            result.append(module)

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

            module_info = GsdmlReader.read_module_info(element, texts)

            submodule = GsdmlSubmodule(
                submodule_id=element.attrib.get("ID", ""),
                name=module_info["name"],
                text_id=module_info["text_id"],
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
    def read_module_info(element: ET.Element, texts: dict[str, str]) -> dict[str, str]:
        result = {
            "name": "",
            "text_id": "",
            "info_text": "",
            "order_number": "",
        }

        module_info = GsdmlReader.find_first_inside(element, "ModuleInfo")

        if module_info is None:
            return result

        name_element = GsdmlReader.find_first_inside(module_info, "Name")
        info_text_element = GsdmlReader.find_first_inside(module_info, "InfoText")
        order_number_element = GsdmlReader.find_first_inside(module_info, "OrderNumber")

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
            if order_number_element.attrib.get("Value", ""):
                result["order_number"] = order_number_element.attrib.get("Value", "")
            elif order_number_element.text:
                result["order_number"] = order_number_element.text.strip()

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

        graphic_ref_element = GsdmlReader.find_first_inside(element, "GraphicItemRef")

        if graphic_ref_element is not None:
            if graphic_ref_element.attrib.get("Value", ""):
                return graphic_ref_element.attrib.get("Value", "")

            if graphic_ref_element.attrib.get("Ref", ""):
                return graphic_ref_element.attrib.get("Ref", "")

            if graphic_ref_element.text:
                return graphic_ref_element.text.strip()

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

        base_name = gsd_file.device.device_name or gsd_file.file_name
        instance_number = len(self.device_instances) + 1

        instance = ProjectDeviceInstance(
            instance_name=f"{base_name}_{instance_number}",
            source_gsd_file_index=source_gsd_file_index,
            gsd_file=gsd_file,
            selected_dap=selected_dap,
        )

        self.device_instances.append(instance)

        return instance


class HardwareCatalogList(QListWidget):
    """
    Правый список GSDML-файлов.

    Из него можно перетаскивать устройство в дерево проекта.
    """

    MIME_TYPE = "application/x-sbp-bet-gsd-file-index"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SingleSelection)

    def startDrag(self, supported_actions):
        item = self.currentItem()

        if item is None:
            return

        file_index = item.data(Qt.UserRole)

        if file_index is None:
            return

        mime = QMimeData()
        mime.setData(self.MIME_TYPE, str(file_index).encode("utf-8"))
        mime.setText(item.text())

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class ProjectTree(QTreeWidget):
    """
    Левое дерево проекта.

    Принимает drag-and-drop из HardwareCatalogList.
    """

    def __init__(self, on_gsd_file_dropped_callback, parent=None):
        super().__init__(parent)

        self.on_gsd_file_dropped_callback = on_gsd_file_dropped_callback

        self.setHeaderLabels(["Дерево проекта"])
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DropOnly)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(HardwareCatalogList.MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(HardwareCatalogList.MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(HardwareCatalogList.MIME_TYPE):
            event.ignore()
            return

        raw_index = bytes(event.mimeData().data(HardwareCatalogList.MIME_TYPE)).decode("utf-8")

        try:
            file_index = int(raw_index)
        except ValueError:
            event.ignore()
            return

        success = self.on_gsd_file_dropped_callback(file_index)

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

        self.project_tree = ProjectTree(self.on_gsd_file_dropped_to_project)
        self.project_tree.itemClicked.connect(self.on_project_tree_item_clicked)

        root_item = QTreeWidgetItem(["Проект SBP-BET"])
        self.project_tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)

        self.main_text_area = QTextEdit()
        self.main_text_area.setReadOnly(True)
        self.main_text_area.setText(
            "SBP-BET\n\n"
            "1. Загрузите GSDML/XML через меню Проект.\n"
            "2. Перетащите устройство из правого каталога в левое дерево проекта.\n"
            "3. При добавлении выберите DAP."
        )

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_title = QLabel("Загруженные GSDML/XML")
        self.hardware_catalog = HardwareCatalogList()
        self.hardware_catalog.itemClicked.connect(self.on_hardware_catalog_item_clicked)

        right_layout.addWidget(right_title)
        right_layout.addWidget(self.hardware_catalog)

        main_splitter.addWidget(self.project_tree)
        main_splitter.addWidget(self.main_text_area)
        main_splitter.addWidget(right_panel)

        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 5)
        main_splitter.setStretchFactor(2, 2)

        self.setCentralWidget(main_splitter)

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
            self.main_text_area.setText(
                "Ошибка чтения XML-файла.\n\n"
                f"Файл: {file_path}\n\n"
                f"Ошибка XML:\n{error}"
            )
            return
        except Exception as error:
            self.main_text_area.setText(
                "Не удалось загрузить GSDML/XML файл.\n\n"
                f"Файл: {file_path}\n\n"
                f"Ошибка:\n{error}"
            )
            return

        display_name = gsd_file.device_name or gsd_file.file_name

        if gsd_file.vendor_name:
            display_name = f"{gsd_file.vendor_name} — {display_name}"

        item = QListWidgetItem(display_name)
        item.setToolTip(gsd_file.file_path)

        file_index = len(self.project.loaded_gsd_files) - 1
        item.setData(Qt.UserRole, file_index)

        self.hardware_catalog.addItem(item)

        self.show_gsd_file_info(gsd_file)

    def on_gsd_file_dropped_to_project(self, file_index: int) -> bool:
        if file_index < 0 or file_index >= len(self.project.loaded_gsd_files):
            return False

        gsd_file = self.project.loaded_gsd_files[file_index]
        device = gsd_file.device

        if not device.device_access_points:
            QMessageBox.warning(
                self,
                "DAP не найден",
                "В выбранном GSDML/XML файле не найден DeviceAccessPointItem."
            )
            return False

        selected_dap = self.ask_user_to_select_dap(device)

        if selected_dap is None:
            return False

        instance = self.project.add_device_instance(file_index, selected_dap)
        self.add_device_instance_to_project_tree(instance)
        self.show_project_device_instance_info(instance)

        return True

    def ask_user_to_select_dap(self, device: GsdmlDevice) -> GsdmlDeviceAccessPoint | None:
        dap_items = []

        for dap in device.device_access_points:
            title_parts = []

            if dap.name:
                title_parts.append(dap.name)

            if dap.dap_id:
                title_parts.append(f"ID: {dap.dap_id}")

            if dap.module_ident_number:
                title_parts.append(f"ModuleIdentNumber: {dap.module_ident_number}")

            dap_items.append(" | ".join(title_parts) if title_parts else "DAP")

        selected_text, ok = QInputDialog.getItem(
            self,
            "Выбор DAP",
            "Выберите DeviceAccessPointItem:",
            dap_items,
            0,
            False,
        )

        if not ok:
            return None

        selected_index = dap_items.index(selected_text)

        return device.device_access_points[selected_index]

    def add_device_instance_to_project_tree(self, instance: ProjectDeviceInstance):
        root_item = self.project_tree.topLevelItem(0)

        device = instance.gsd_file.device

        device_title = instance.instance_name

        if device.vendor_name:
            device_title = f"{device.vendor_name} — {device_title}"

        device_item = QTreeWidgetItem([device_title])
        device_item.setData(0, Qt.UserRole, instance)

        dap = instance.selected_dap

        dap_item = QTreeWidgetItem([f"DAP: {dap.name or dap.dap_id or '-'}"])
        dap_item.setData(0, Qt.UserRole, dap)

        dap_item.addChild(QTreeWidgetItem([f"ID: {dap.dap_id or '-'}"]))
        dap_item.addChild(QTreeWidgetItem([f"ModuleIdentNumber: {dap.module_ident_number or '-'}"]))
        dap_item.addChild(QTreeWidgetItem([f"FixedInSlots: {dap.fixed_in_slots or '-'}"]))
        dap_item.addChild(QTreeWidgetItem([f"Подмодулей: {len(dap.submodules)}"]))

        modules_root_item = QTreeWidgetItem(["Доступные модули"])

        for module in device.modules:
            module_item = QTreeWidgetItem([module.name or module.module_id or "Module"])
            module_item.setData(0, Qt.UserRole, module)

            module_item.addChild(QTreeWidgetItem([f"ID: {module.module_id or '-'}"]))
            module_item.addChild(QTreeWidgetItem([f"ModuleIdentNumber: {module.module_ident_number or '-'}"]))
            module_item.addChild(QTreeWidgetItem([f"OrderNumber: {module.order_number or '-'}"]))
            module_item.addChild(QTreeWidgetItem([f"Подмодулей: {len(module.submodules)}"]))

            modules_root_item.addChild(module_item)

        device_item.addChild(dap_item)
        device_item.addChild(modules_root_item)

        root_item.addChild(device_item)

        root_item.setExpanded(True)
        device_item.setExpanded(True)
        dap_item.setExpanded(True)
        modules_root_item.setExpanded(True)

    def show_gsd_file_info(self, gsd_file: ProjectGsdFile):
        device = gsd_file.device

        self.main_text_area.setText(
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
            f"GraphicsList записей: {len(device.graphics)}\n"
            f"DeviceAccessPointItem: {len(device.device_access_points)}\n"
            f"ModuleItem: {len(device.modules)}\n\n"

            f"{self.format_graphics_info(device)}\n"
            f"{self.format_dap_info(device)}\n"
            f"{self.format_modules_info(device)}\n"

            f"Экземпляров устройств в проекте: {len(self.project.device_instances)}\n"
            f"Всего GSDML/XML файлов в проекте: {len(self.project.loaded_gsd_files)}"
        )

    def show_project_device_instance_info(self, instance: ProjectDeviceInstance):
        device = instance.gsd_file.device
        dap = instance.selected_dap

        self.main_text_area.setText(
            "Устройство добавлено в проект:\n\n"
            f"Экземпляр: {instance.instance_name}\n"
            f"Производитель: {device.vendor_name or '-'}\n"
            f"Устройство: {device.device_name or '-'}\n\n"

            f"Выбранный DAP:\n"
            f"  ID: {dap.dap_id or '-'}\n"
            f"  Название: {dap.name or '-'}\n"
            f"  ModuleIdentNumber: {dap.module_ident_number or '-'}\n"
            f"  FixedInSlots: {dap.fixed_in_slots or '-'}\n"
            f"  Подмодулей: {len(dap.submodules)}\n\n"

            f"Доступных модулей: {len(device.modules)}\n"
            f"Экземпляров устройств в проекте: {len(self.project.device_instances)}"
        )

    def show_module_info(self, module: GsdmlModule):
        input_count = 0
        output_count = 0

        for submodule in module.submodules:
            input_count += len(submodule.input_items)
            output_count += len(submodule.output_items)

        self.main_text_area.setText(
            "GSDML модуль:\n\n"
            f"Название: {module.name or '-'}\n"
            f"ID: {module.module_id or '-'}\n"
            f"ModuleIdentNumber: {module.module_ident_number or '-'}\n"
            f"OrderNumber: {module.order_number or '-'}\n"
            f"Подмодулей: {len(module.submodules)}\n"
            f"Input DataItem: {input_count}\n"
            f"Output DataItem: {output_count}\n\n"
            f"{self.format_submodules_info(module.submodules)}"
        )

    def show_dap_info(self, dap: GsdmlDeviceAccessPoint):
        self.main_text_area.setText(
            "DeviceAccessPointItem:\n\n"
            f"Название: {dap.name or '-'}\n"
            f"ID: {dap.dap_id or '-'}\n"
            f"ModuleIdentNumber: {dap.module_ident_number or '-'}\n"
            f"FixedInSlots: {dap.fixed_in_slots or '-'}\n"
            f"GraphicRef: {dap.graphics_ref or '-'}\n"
            f"Подмодулей: {len(dap.submodules)}\n\n"
            f"{self.format_submodules_info(dap.submodules)}"
        )

    def format_graphics_info(self, device: GsdmlDevice) -> str:
        if not device.graphics:
            return "GraphicsList: графические элементы не найдены.\n\n"

        lines = ["GraphicsList:"]

        for graphic in device.graphics:
            lines.append(f"  ID: {graphic.graphic_id or '-'}")
            lines.append(f"  GraphicFile: {graphic.graphic_file or '-'}")

            if graphic.file_exists:
                lines.append(f"  Файл найден: {graphic.resolved_file_path}")
            else:
                lines.append("  Файл найден: нет")

            lines.append("")

        return "\n".join(lines)

    def format_dap_info(self, device: GsdmlDevice) -> str:
        if not device.device_access_points:
            return "DeviceAccessPointItem: не найдено.\n\n"

        lines = ["DeviceAccessPointItem:"]

        for dap in device.device_access_points:
            lines.append(f"  ID: {dap.dap_id or '-'}")
            lines.append(f"  Название: {dap.name or '-'}")
            lines.append(f"  ModuleIdentNumber: {dap.module_ident_number or '-'}")
            lines.append(f"  FixedInSlots: {dap.fixed_in_slots or '-'}")
            lines.append(f"  GraphicRef: {dap.graphics_ref or '-'}")
            lines.append(f"  Подмодулей: {len(dap.submodules)}")
            lines.append("")

        return "\n".join(lines)

    def format_modules_info(self, device: GsdmlDevice) -> str:
        if not device.modules:
            return "ModuleItem: не найдено.\n\n"

        lines = ["ModuleItem:"]

        max_modules_to_show = 20

        for index, module in enumerate(device.modules[:max_modules_to_show], start=1):
            input_count = 0
            output_count = 0

            for submodule in module.submodules:
                input_count += len(submodule.input_items)
                output_count += len(submodule.output_items)

            lines.append(f"  {index}. {module.name or module.module_id or '-'}")
            lines.append(f"     ID: {module.module_id or '-'}")
            lines.append(f"     ModuleIdentNumber: {module.module_ident_number or '-'}")
            lines.append(f"     OrderNumber: {module.order_number or '-'}")
            lines.append(f"     Подмодулей: {len(module.submodules)}")
            lines.append(f"     Input DataItem: {input_count}")
            lines.append(f"     Output DataItem: {output_count}")
            lines.append("")

        if len(device.modules) > max_modules_to_show:
            lines.append(
                f"  ... показано {max_modules_to_show} из {len(device.modules)} модулей."
            )
            lines.append("")

        return "\n".join(lines)

    def format_submodules_info(self, submodules: list[GsdmlSubmodule]) -> str:
        if not submodules:
            return "Подмодули: не найдены."

        lines = ["Подмодули:"]

        for submodule in submodules:
            lines.append(f"  Название: {submodule.name or '-'}")
            lines.append(f"  ID: {submodule.submodule_id or '-'}")
            lines.append(f"  SubmoduleIdentNumber: {submodule.submodule_ident_number or '-'}")
            lines.append(f"  Тип: {submodule.kind or '-'}")
            lines.append(f"  Input DataItem: {len(submodule.input_items)}")
            lines.append(f"  Output DataItem: {len(submodule.output_items)}")
            lines.append("")

        return "\n".join(lines)

    def on_hardware_catalog_item_clicked(self, item: QListWidgetItem):
        file_index = item.data(Qt.UserRole)

        if file_index is None:
            return

        if file_index < 0 or file_index >= len(self.project.loaded_gsd_files):
            return

        gsd_file = self.project.loaded_gsd_files[file_index]
        self.show_gsd_file_info(gsd_file)

    def on_project_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        obj = item.data(0, Qt.UserRole)

        if isinstance(obj, ProjectDeviceInstance):
            self.show_project_device_instance_info(obj)
            return

        if isinstance(obj, GsdmlDeviceAccessPoint):
            self.show_dap_info(obj)
            return

        if isinstance(obj, GsdmlModule):
            self.show_module_info(obj)
            return

        self.main_text_area.setText(item.text(0))


def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()