import json
import xml.etree.ElementTree as ET

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spb_bet.models import (
    GsdmlDevice,
    GsdmlDeviceAccessPoint,
    GsdmlModule,
    GsdmlModuleRef,
    GsdmlSubmodule,
    ProjectDeviceInstance,
    ProjectGsdFile,
)
from spb_bet.project import SpbBetProject
from spb_bet.ui.widgets import HardwareCatalogTree, ProjectTree


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.project = SpbBetProject()

        self.setWindowTitle("SPB-BET")
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

        root_item = QTreeWidgetItem(["Проект SPB-BET"])
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
            "SPB-BET\n\n"
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
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
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
            "GSDML/XML files (*.gsdml *.xml);;All files (*.*)",
        )

        if not file_path:
            return

        if self.project.contains_gsd_file(file_path):
            QMessageBox.information(
                self,
                "Файл уже добавлен",
                "Этот GSDML/XML файл уже добавлен в проект.",
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