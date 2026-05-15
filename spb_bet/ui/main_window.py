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
    GsdmlIoDataItem,
    GsdmlModule,
    GsdmlModuleRef,
    GsdmlSubmodule,
    ProjectDeviceInstance,
    ProjectGsdFile,
    ProjectSlot,
)
from spb_bet.project import SbpBetProject
from spb_bet.ui.widgets import HardwareCatalogTree, ProjectTree


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

        self.composition_table = QTableWidget()
        self.composition_table.setColumnCount(9)
        self.composition_table.setHorizontalHeaderLabels(
            [
                "Rule",
                "Slots",
                "Module",
                "OrderNumber",
                "Category",
                "Input bytes",
                "Output bytes",
                "Input items",
                "Output items",
            ]
        )
        self.composition_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.composition_table.horizontalHeader().setStretchLastSection(True)

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
        self.center_tabs.addTab(self.composition_table, "Состав устройства")
        self.center_tabs.addTab(self.io_data_table, "IO Data")
        self.center_tabs.addTab(self.raw_text_area, "Raw")

        self.set_overview_text(
            "SBP-BET\n\n"
            "1. Загрузите GSDML/XML через меню Проект.\n"
            "2. Справа появится дерево Hardware Catalog.\n"
            "3. Перетащите конкретный DAP справа налево, чтобы добавить устройство в проект.\n"
            "4. При выборе DAP смотрите вкладку «Состав устройства»."
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

    def clear_composition_table(self):
        self.composition_table.setRowCount(0)

    def get_io_item_bit_length(self, item: GsdmlIoDataItem) -> int:
        if item.bit_length:
            try:
                return int(item.bit_length)
            except ValueError:
                pass

        data_type = item.data_type.lower()

        known_sizes = {
            "boolean": 1,
            "bit": 1,
            "integer8": 8,
            "unsigned8": 8,
            "integer16": 16,
            "unsigned16": 16,
            "integer32": 32,
            "unsigned32": 32,
            "float32": 32,
            "float64": 64,
        }

        if data_type in known_sizes:
            return known_sizes[data_type]

        digits = "".join(ch for ch in item.data_type if ch.isdigit())

        if digits:
            try:
                return int(digits)
            except ValueError:
                return 0

        return 0

    def get_module_io_summary(self, module: GsdmlModule) -> dict:
        input_bits = 0
        output_bits = 0
        input_items = 0
        output_items = 0

        for submodule in module.submodules:
            for item in submodule.input_items:
                input_items += 1
                input_bits += self.get_io_item_bit_length(item)

            for item in submodule.output_items:
                output_items += 1
                output_bits += self.get_io_item_bit_length(item)

        return {
            "input_bits": input_bits,
            "output_bits": output_bits,
            "input_bytes": (input_bits + 7) // 8,
            "output_bytes": (output_bits + 7) // 8,
            "input_items": input_items,
            "output_items": output_items,
        }

    def get_module_ref_rule(self, module_ref: GsdmlModuleRef) -> tuple[str, str]:
        if module_ref.fixed_in_slots:
            return "FixedInSlots", module_ref.fixed_in_slots

        if module_ref.used_in_slots:
            return "UsedInSlots", module_ref.used_in_slots

        if module_ref.allowed_in_slots:
            return "AllowedInSlots", module_ref.allowed_in_slots

        return "Unknown", ""

    def fill_composition_table_from_dap(self, dap: GsdmlDeviceAccessPoint):
        rows = []

        for module_ref in dap.module_refs:
            module = module_ref.module
            rule, slots = self.get_module_ref_rule(module_ref)

            if module is None:
                rows.append(
                    {
                        "rule": rule,
                        "slots": slots,
                        "module": module_ref.module_item_target,
                        "order_number": "",
                        "category": "",
                        "input_bytes": "",
                        "output_bytes": "",
                        "input_items": "",
                        "output_items": "",
                    }
                )
                continue

            io_summary = self.get_module_io_summary(module)

            rows.append(
                {
                    "rule": rule,
                    "slots": slots,
                    "module": module.name or module.module_id,
                    "order_number": module.order_number,
                    "category": module.category_name,
                    "input_bytes": io_summary["input_bytes"],
                    "output_bytes": io_summary["output_bytes"],
                    "input_items": io_summary["input_items"],
                    "output_items": io_summary["output_items"],
                }
            )

        self.composition_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                row["rule"],
                row["slots"],
                row["module"],
                row["order_number"],
                row["category"],
                row["input_bytes"],
                row["output_bytes"],
                row["input_items"],
                row["output_items"],
            ]

            for column_index, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                self.composition_table.setItem(row_index, column_index, table_item)

        self.composition_table.resizeColumnsToContents()

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
            self.clear_composition_table()
            self.set_raw_data({})
            return
        except Exception as error:
            self.set_overview_text(
                "Не удалось загрузить GSDML/XML файл.\n\n"
                f"Файл: {file_path}\n\n"
                f"Ошибка:\n{error}"
            )
            self.clear_io_table()
            self.clear_composition_table()
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

        slots_root_item = QTreeWidgetItem(["Слоты устройства"])
        slots_root_item.setData(0, Qt.UserRole, {"type": "slots_root", "instance": instance})

        for slot in instance.slots:
            slot_item = QTreeWidgetItem([self.format_project_slot_title(slot, dap)])
            slot_item.setData(0, Qt.UserRole, slot)

            slot_item.addChild(QTreeWidgetItem([f"Номер слота: {slot.slot_number}"]))
            slot_item.addChild(QTreeWidgetItem([f"Тип слота: {slot.slot_kind}"]))

            if slot.slot_kind == "dap":
                slot_item.addChild(QTreeWidgetItem([f"DAP: {dap.display_name or dap.name or dap.dap_id or '-'}"]))
                slot_item.addChild(QTreeWidgetItem([f"ID: {dap.dap_id or '-'}"]))
                slot_item.addChild(QTreeWidgetItem([f"OrderNumber: {dap.order_number or '-'}"]))

            if slot.installed_module is not None:
                module = slot.installed_module
                slot_item.addChild(QTreeWidgetItem([f"Модуль: {module.name or module.module_id or '-'}"]))
                slot_item.addChild(QTreeWidgetItem([f"ID: {module.module_id or '-'}"]))
                slot_item.addChild(QTreeWidgetItem([f"OrderNumber: {module.order_number or '-'}"]))
                slot_item.addChild(QTreeWidgetItem([f"Подмодулей: {len(module.submodules)}"]))

            if slot.allowed_modules:
                allowed_root = QTreeWidgetItem([f"Доступные варианты: {len(slot.allowed_modules)}"])

                for allowed_module in slot.allowed_modules:
                    allowed_root.addChild(
                        QTreeWidgetItem(
                            [
                                allowed_module.name
                                or allowed_module.category_name
                                or allowed_module.module_id
                                or "Module"
                            ]
                        )
                    )

                slot_item.addChild(allowed_root)

            slots_root_item.addChild(slot_item)

        device_item.addChild(slots_root_item)

        root_item.addChild(device_item)

        root_item.setExpanded(True)
        device_item.setExpanded(True)
        slots_root_item.setExpanded(True)

    def format_project_slot_title(
            self,
            slot: ProjectSlot,
            dap: GsdmlDeviceAccessPoint,
    ) -> str:
        if slot.slot_kind == "dap":
            dap_name = dap.display_name or dap.name or dap.dap_id or "DAP"
            return f"Slot {slot.slot_number}: DAP {dap_name}"

        if slot.installed_module is not None:
            module = slot.installed_module
            module_name = module.name or module.category_name or module.module_id or "Module"

            if slot.slot_kind == "fixed":
                return f"Slot {slot.slot_number}: {module_name} [fixed]"

            if slot.slot_kind == "used":
                return f"Slot {slot.slot_number}: {module_name} [used]"

            return f"Slot {slot.slot_number}: {module_name}"

        if slot.allowed_modules:
            return f"Slot {slot.slot_number}: пустой [доступно {len(slot.allowed_modules)}]"

        return f"Slot {slot.slot_number}: пустой"

    def show_gsd_file_info(self, gsd_file: ProjectGsdFile):
        device = gsd_file.device
        file_name_info = gsd_file.file_name_info

        self.clear_io_table()
        self.clear_composition_table()

        self.set_overview_text(
            "GSDML/XML файл:\n\n"
            f"Проект: {self.project.project_name}\n"
            f"Имя файла: {gsd_file.file_name}\n"
            f"Расширение: {gsd_file.file_extension}\n"
            f"Полный путь: {gsd_file.file_path}\n\n"

            f"Имя соответствует GSDML-шаблону: {file_name_info.is_valid_gsdml_name}\n"
            f"Версия из имени файла: {file_name_info.gsdml_version or '-'}\n"
            f"Производитель из имени файла: {file_name_info.vendor_from_name or '-'}\n"
            f"Семейство устройства из имени файла: {file_name_info.device_family_from_name or '-'}\n"
            f"Дата файла из имени файла: {file_name_info.date_from_name or '-'}\n\n"

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
                    "file_name_info": {
                        "raw_file_name": file_name_info.raw_file_name,
                        "is_valid_gsdml_name": file_name_info.is_valid_gsdml_name,
                        "gsdml_version": file_name_info.gsdml_version,
                        "vendor_from_name": file_name_info.vendor_from_name,
                        "device_family_from_name": file_name_info.device_family_from_name,
                        "date_from_name": file_name_info.date_from_name,
                    },
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

        self.fill_io_table_from_project_instance(instance)
        self.fill_composition_table_from_project_instance(instance)

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
            f"  Слотов построено: {len(instance.slots)}\n\n"

            f"{self.format_project_slots_info(instance)}"
        )

        self.set_raw_data(
            {
                "instance_name": instance.instance_name,
                "source_gsd_file_index": instance.source_gsd_file_index,
                "selected_dap": self.dap_to_dict(dap),
                "slots": [
                    self.project_slot_to_dict(slot)
                    for slot in instance.slots
                ],
            }
        )

    def show_project_slot_info(self, slot: ProjectSlot):
        self.clear_composition_table()

        if slot.installed_module is not None:
            self.fill_io_table_from_submodules(slot.installed_module.submodules)
        else:
            self.clear_io_table()

        overview_lines = [
            "Слот устройства:\n",
            f"Номер слота: {slot.slot_number}",
            f"Тип слота: {slot.slot_kind}",
            "",
        ]

        if slot.slot_kind == "dap":
            overview_lines.append("Это слот базового устройства / DAP.")

        if slot.installed_module is not None:
            module = slot.installed_module

            overview_lines.extend(
                [
                    "Установленный модуль:",
                    f"  Название: {module.name or '-'}",
                    f"  ID: {module.module_id or '-'}",
                    f"  OrderNumber: {module.order_number or '-'}",
                    f"  Category: {module.category_name or '-'}",
                    f"  Подмодулей: {len(module.submodules)}",
                    "",
                ]
            )

        if slot.allowed_modules:
            overview_lines.append("Доступные варианты для установки:")

            for module in slot.allowed_modules:
                overview_lines.append(
                    f"  - {module.name or module.category_name or module.module_id or '-'}"
                )

        if not slot.installed_module and not slot.allowed_modules and slot.slot_kind != "dap":
            overview_lines.append("Для этого слота нет установленного модуля и доступных вариантов.")

        self.set_overview_text("\n".join(overview_lines))
        self.set_raw_data(self.project_slot_to_dict(slot))

    def format_project_slots_info(self, instance: ProjectDeviceInstance) -> str:
        if not instance.slots:
            return "Слоты устройства: не построены."

        lines = ["Слоты устройства:"]

        for slot in instance.slots:
            if slot.slot_kind == "dap":
                lines.append(f"  Slot {slot.slot_number}: DAP")
                continue

            if slot.installed_module is not None:
                module = slot.installed_module
                module_name = module.name or module.module_id or "-"
                lines.append(f"  Slot {slot.slot_number}: {module_name} [{slot.slot_kind}]")
                continue

            if slot.allowed_modules:
                lines.append(
                    f"  Slot {slot.slot_number}: пустой, доступно вариантов: {len(slot.allowed_modules)}"
                )
                continue

            lines.append(f"  Slot {slot.slot_number}: пустой")

        return "\n".join(lines)

    def project_slot_to_dict(self, slot: ProjectSlot) -> dict:
        return {
            "slot_number": slot.slot_number,
            "slot_kind": slot.slot_kind,
            "installed_module": self.module_to_dict(slot.installed_module)
            if slot.installed_module is not None
            else None,
            "allowed_modules": [
                self.module_to_dict(module)
                for module in slot.allowed_modules
            ],
            "source_module_ref": slot.source_module_ref.attributes
            if slot.source_module_ref is not None
            else None,
        }

    def fill_io_table_from_project_instance(self, instance: ProjectDeviceInstance):
        submodules = []

        for slot in instance.slots:
            if slot.installed_module is not None:
                submodules.extend(slot.installed_module.submodules)

        self.fill_io_table_from_submodules(submodules)

    def fill_composition_table_from_project_instance(self, instance: ProjectDeviceInstance):
        rows = []

        for slot in instance.slots:
            if slot.slot_kind == "dap":
                rows.append(
                    {
                        "rule": "DAP",
                        "slots": slot.slot_number,
                        "module": instance.selected_dap.display_name or instance.selected_dap.name or "DAP",
                        "order_number": instance.selected_dap.order_number,
                        "category": instance.selected_dap.category_name,
                        "input_bytes": "",
                        "output_bytes": "",
                        "input_items": "",
                        "output_items": "",
                    }
                )
                continue

            if slot.installed_module is not None:
                module = slot.installed_module
                io_summary = self.get_module_io_summary(module)

                rows.append(
                    {
                        "rule": slot.slot_kind,
                        "slots": slot.slot_number,
                        "module": module.name or module.module_id,
                        "order_number": module.order_number,
                        "category": module.category_name,
                        "input_bytes": io_summary["input_bytes"],
                        "output_bytes": io_summary["output_bytes"],
                        "input_items": io_summary["input_items"],
                        "output_items": io_summary["output_items"],
                    }
                )
                continue

            if slot.allowed_modules:
                rows.append(
                    {
                        "rule": "allowed",
                        "slots": slot.slot_number,
                        "module": f"Пустой слот, вариантов: {len(slot.allowed_modules)}",
                        "order_number": "",
                        "category": "",
                        "input_bytes": "",
                        "output_bytes": "",
                        "input_items": "",
                        "output_items": "",
                    }
                )

        self.composition_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                row["rule"],
                row["slots"],
                row["module"],
                row["order_number"],
                row["category"],
                row["input_bytes"],
                row["output_bytes"],
                row["input_items"],
                row["output_items"],
            ]

            for column_index, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                self.composition_table.setItem(row_index, column_index, table_item)

        self.composition_table.resizeColumnsToContents()

    def show_dap_info(self, dap: GsdmlDeviceAccessPoint):
        self.fill_io_table_from_dap(dap)
        self.fill_composition_table_from_dap(dap)

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
        self.clear_composition_table()

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

        self.clear_composition_table()

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
            self.clear_composition_table()
            self.set_raw_data({})
            return

        item_type = payload.get("type")
        file_index = payload.get("file_index")

        if file_index is None:
            self.set_overview_text(item.text(0))
            self.clear_io_table()
            self.clear_composition_table()
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

        self.set_overview_text(item.text(0))
        self.clear_io_table()
        self.clear_composition_table()
        self.set_raw_data({})

    def on_project_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        obj = item.data(0, Qt.UserRole)

        if isinstance(obj, ProjectDeviceInstance):
            self.show_project_device_instance_info(obj)
            return

        if isinstance(obj, ProjectSlot):
            self.show_project_slot_info(obj)
            return

        if isinstance(obj, GsdmlDeviceAccessPoint):
            self.show_dap_info(obj)
            return

        if isinstance(obj, GsdmlModuleRef):
            self.show_module_ref_info(obj)
            return

        self.set_overview_text(item.text(0))
        self.clear_io_table()
        self.clear_composition_table()
        self.set_raw_data({})