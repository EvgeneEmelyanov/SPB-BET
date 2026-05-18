import json
import xml.etree.ElementTree as ET

import wx
import wx.grid as gridlib

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


class ProjectTreeDropTarget(wx.TextDropTarget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

    def OnDropText(self, x, y, data):
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return False

        if payload.get("type") != "dap":
            wx.MessageBox(
                "В дерево проекта можно перетащить только DAP / вариант устройства.",
                "Неверный тип объекта",
                wx.OK | wx.ICON_WARNING,
            )
            return False

        wx.CallAfter(self.main_window.on_dap_dropped_to_project, payload)
        return True


class SlotDropTarget(wx.TextDropTarget):
    def __init__(self, main_window, slot: ProjectSlot):
        super().__init__()
        self.main_window = main_window
        self.slot = slot

    def OnDropText(self, x, y, data):
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return False

        if payload.get("type") != "module":
            wx.MessageBox(
                "В слот можно перетащить только модуль.",
                "Неверный тип объекта",
                wx.OK | wx.ICON_WARNING,
            )
            return False

        wx.CallAfter(
            self.main_window.on_module_dropped_to_slot,
            payload,
            self.slot,
        )

        return True


class SlotCardPanel(wx.Panel):
    def __init__(
            self,
            parent,
            main_window,
            slot: ProjectSlot,
            dap: GsdmlDeviceAccessPoint,
    ):
        super().__init__(parent, style=wx.BORDER_SIMPLE)

        self.main_window = main_window
        self.slot = slot
        self.dap = dap

        self.SetMinSize((190, 105))

        if self.slot.slot_kind == "dap":
            self.SetBackgroundColour(wx.Colour(230, 240, 255))
        elif self.slot.installed_module is not None:
            self.SetBackgroundColour(wx.Colour(230, 255, 230))
        elif self.slot.allowed_modules:
            self.SetBackgroundColour(wx.Colour(255, 250, 220))
        else:
            self.SetBackgroundColour(wx.Colour(245, 245, 245))

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.title_label = wx.StaticText(self, label=self.make_title())
        self.title_label.Wrap(160)

        self.status_label = wx.StaticText(self, label=self.make_status())
        self.status_label.Wrap(160)

        sizer.Add(self.title_label, 0, wx.EXPAND | wx.ALL, 6)
        sizer.Add(self.status_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.SetSizer(sizer)

        self.bind_click_handlers()

        if self.can_accept_module():
            self.SetDropTarget(SlotDropTarget(main_window, slot))

    def bind_click_handlers(self):
        for control in [self, self.title_label, self.status_label]:
            control.Bind(wx.EVT_LEFT_UP, self.on_left_click)

    def make_title(self) -> str:
        if self.slot.slot_kind == "dap":
            return f"Slot {self.slot.slot_number}\nDAP"

        if self.slot.installed_module is not None:
            module = self.slot.installed_module
            return f"Slot {self.slot.slot_number}\n{module.name or module.module_id or 'Module'}"

        return f"Slot {self.slot.slot_number}\nПустой слот"

    def make_status(self) -> str:
        if self.slot.slot_kind == "dap":
            return self.dap.display_name or self.dap.name or self.dap.dap_id or "-"

        if self.slot.installed_module is not None:
            return f"Тип: {self.slot.slot_kind}"

        if self.slot.allowed_modules:
            return f"Можно установить: {len(self.slot.allowed_modules)}"

        return "Нет доступных модулей"

    def can_accept_module(self) -> bool:
        return (
                self.slot.installed_module is None
                and self.slot.slot_kind != "dap"
                and len(self.slot.allowed_modules) > 0
        )

    def on_left_click(self, event):
        wx.CallAfter(self.main_window.show_project_slot_info, self.slot)
        event.Skip()


class MainWindow(wx.Frame):
    def __init__(self):
        super().__init__(
            parent=None,
            title="SBP-BET",
            size=(1600, 920),
        )

        self.project = SbpBetProject()

        self.create_menu()
        self.create_main_layout()

        self.Centre()

    def create_menu(self):
        menu_bar = wx.MenuBar()

        project_menu = wx.Menu()

        load_gsd_item = project_menu.Append(
            wx.ID_OPEN,
            "Загрузить GSDML/XML",
            "Загрузить GSDML/XML файл",
        )
        self.Bind(wx.EVT_MENU, self.on_load_gsd_clicked, load_gsd_item)

        project_menu.AppendSeparator()

        exit_item = project_menu.Append(
            wx.ID_EXIT,
            "Выход",
            "Закрыть программу",
        )
        self.Bind(wx.EVT_MENU, self.on_exit_clicked, exit_item)

        menu_bar.Append(project_menu, "Проект")

        self.SetMenuBar(menu_bar)

    def create_main_layout(self):
        main_panel = wx.Panel(self)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.splitter_left = wx.SplitterWindow(main_panel)
        self.splitter_right = wx.SplitterWindow(self.splitter_left)

        # Левая часть — дерево проекта
        left_panel = wx.Panel(self.splitter_left)
        left_sizer = wx.BoxSizer(wx.VERTICAL)

        left_title = wx.StaticText(left_panel, label="Дерево проекта")
        self.project_tree = wx.TreeCtrl(
            left_panel,
            style=wx.TR_DEFAULT_STYLE | wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT,
        )

        self.project_tree.SetDropTarget(ProjectTreeDropTarget(self))

        self.project_root_item = self.project_tree.AddRoot("Проект SBP-BET")
        self.project_tree.Expand(self.project_root_item)

        self.project_tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_project_tree_item_selected)

        left_sizer.Add(left_title, 0, wx.EXPAND | wx.ALL, 4)
        left_sizer.Add(self.project_tree, 1, wx.EXPAND | wx.ALL, 4)
        left_panel.SetSizer(left_sizer)

        # Центральная часть — верхняя графика + нижнее описание
        center_panel = wx.Panel(self.splitter_right)
        center_sizer = wx.BoxSizer(wx.VERTICAL)

        self.center_splitter = wx.SplitterWindow(center_panel)

        # Верхняя часть — графическое представление устройства
        self.graphics_panel = wx.Panel(self.center_splitter)
        graphics_sizer = wx.BoxSizer(wx.VERTICAL)

        self.graphics_title = wx.StaticText(
            self.graphics_panel,
            label="Графическое представление устройства",
        )

        self.graphics_scroll = wx.ScrolledWindow(
            self.graphics_panel,
            style=wx.VSCROLL | wx.HSCROLL,
        )
        self.graphics_scroll.SetScrollRate(10, 10)

        self.graphics_content_sizer = wx.BoxSizer(wx.VERTICAL)

        self.graphics_header_sizer = wx.BoxSizer(wx.VERTICAL)

        self.slots_grid_sizer = wx.FlexGridSizer(cols=6, hgap=8, vgap=8)
        for col_index in range(6):
            self.slots_grid_sizer.AddGrowableCol(col_index, 1)

        self.graphics_content_sizer.Add(
            self.graphics_header_sizer,
            0,
            wx.EXPAND | wx.ALL,
            6,
        )

        self.graphics_content_sizer.Add(
            self.slots_grid_sizer,
            0,
            wx.EXPAND | wx.ALL,
            6,
        )

        self.graphics_scroll.SetSizer(self.graphics_content_sizer)

        graphics_sizer.Add(self.graphics_title, 0, wx.EXPAND | wx.ALL, 4)
        graphics_sizer.Add(self.graphics_scroll, 1, wx.EXPAND | wx.ALL, 4)

        self.graphics_panel.SetSizer(graphics_sizer)

        # Нижняя часть — вкладки с текстом и таблицами
        bottom_panel = wx.Panel(self.center_splitter)
        bottom_sizer = wx.BoxSizer(wx.VERTICAL)

        self.center_tabs = wx.Notebook(bottom_panel)

        self.overview_text_area = wx.TextCtrl(
            self.center_tabs,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
        )

        self.composition_table = gridlib.Grid(self.center_tabs)
        self.create_grid(
            self.composition_table,
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
            ],
        )

        self.io_data_table = gridlib.Grid(self.center_tabs)
        self.create_grid(
            self.io_data_table,
            [
                "Direction",
                "Submodule",
                "Name",
                "DataType",
                "BitLength",
                "UseAsBits",
                "TextId",
                "Attributes",
            ],
        )

        self.raw_text_area = wx.TextCtrl(
            self.center_tabs,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
        )

        self.center_tabs.AddPage(self.overview_text_area, "Обзор")
        self.center_tabs.AddPage(self.composition_table, "Состав устройства")
        self.center_tabs.AddPage(self.io_data_table, "IO Data")
        self.center_tabs.AddPage(self.raw_text_area, "Raw")

        bottom_sizer.Add(self.center_tabs, 1, wx.EXPAND | wx.ALL, 4)
        bottom_panel.SetSizer(bottom_sizer)

        self.center_splitter.SplitHorizontally(self.graphics_panel, bottom_panel)
        self.center_splitter.SetSashGravity(0.45)
        self.center_splitter.SetMinimumPaneSize(160)

        center_sizer.Add(self.center_splitter, 1, wx.EXPAND)
        center_panel.SetSizer(center_sizer)

        self.show_graphics_placeholder()

        # Правая часть — Hardware Catalog
        right_panel = wx.Panel(self.splitter_right)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        right_title = wx.StaticText(right_panel, label="Загруженные GSDML/XML")

        self.hardware_catalog = wx.TreeCtrl(
            right_panel,
            style=wx.TR_DEFAULT_STYLE | wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT,
        )

        self.hardware_root_item = self.hardware_catalog.AddRoot("Hardware Catalog")
        self.hardware_catalog.Bind(wx.EVT_TREE_BEGIN_DRAG, self.on_hardware_tree_begin_drag)
        self.hardware_catalog.Expand(self.hardware_root_item)

        self.hardware_catalog.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_hardware_catalog_item_selected)

        right_sizer.Add(right_title, 0, wx.EXPAND | wx.ALL, 4)
        right_sizer.Add(self.hardware_catalog, 1, wx.EXPAND | wx.ALL, 4)

        right_panel.SetSizer(right_sizer)

        self.splitter_right.SplitVertically(center_panel, right_panel)
        self.splitter_right.SetSashGravity(0.72)
        self.splitter_right.SetMinimumPaneSize(250)

        self.splitter_left.SplitVertically(left_panel, self.splitter_right)
        self.splitter_left.SetSashGravity(0.22)
        self.splitter_left.SetMinimumPaneSize(220)

        main_sizer.Add(self.splitter_left, 1, wx.EXPAND)

        main_panel.SetSizer(main_sizer)
        main_panel.Layout()

        wx.CallAfter(self.apply_initial_layout)

        self.set_overview_text(
            "SBP-BET\n\n"
            "1. Загрузите GSDML/XML через меню Проект.\n"
            "2. Справа появится Hardware Catalog.\n"
            "3. Перетащите DAP из правого дерева в левое дерево проекта.\n"
            "4. В верхнем центральном окне появятся слоты устройства.\n"
            "5. Перетащите модуль из правого дерева на пустой слот."
        )

    def apply_initial_layout(self):
        """
        Начальные размеры панелей:
        - слева дерево проекта;
        - справа Hardware Catalog;
        - центр делится на верхнюю графику и нижнее описание.
        """

        try:
            self.Layout()

            frame_width, frame_height = self.GetClientSize()

            left_width = 315
            right_width = 350

            self.splitter_left.SetSashPosition(left_width)

            center_and_right_width = max(600, frame_width - left_width)
            center_width = max(500, center_and_right_width - right_width)

            self.splitter_right.SetSashPosition(center_width)

            top_height = max(260, int(frame_height * 0.62))
            self.center_splitter.SetSashPosition(top_height)

            self.splitter_left.UpdateSize()
            self.splitter_right.UpdateSize()
            self.center_splitter.UpdateSize()

            self.Layout()

        except Exception as error:
            print(f"Ошибка начальной раскладки окна: {error}")

    def on_exit_clicked(self, event):
        self.Close()

    def create_grid(self, grid: gridlib.Grid, columns: list[str]):
        grid.CreateGrid(0, len(columns))

        for index, column_name in enumerate(columns):
            grid.SetColLabelValue(index, column_name)

        grid.EnableEditing(False)
        grid.EnableDragGridSize(False)
        grid.SetRowLabelSize(40)
        grid.AutoSizeColumns()

    def clear_grid(self, grid: gridlib.Grid):
        rows = grid.GetNumberRows()

        if rows > 0:
            grid.DeleteRows(0, rows)

    def fill_grid(self, grid: gridlib.Grid, rows: list[list[str]]):
        self.clear_grid(grid)

        if rows:
            grid.AppendRows(len(rows))

        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                grid.SetCellValue(row_index, column_index, str(value))

        grid.AutoSizeColumns()

    def set_overview_text(self, text: str):
        self.overview_text_area.SetValue(text)
        self.center_tabs.SetSelection(0)

    def set_raw_data(self, data):
        self.raw_text_area.SetValue(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=4,
            )
        )

    def clear_io_table(self):
        self.clear_grid(self.io_data_table)

    def clear_composition_table(self):
        self.clear_grid(self.composition_table)

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
                    [
                        rule,
                        slots,
                        module_ref.module_item_target,
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                    ]
                )
                continue

            io_summary = self.get_module_io_summary(module)

            rows.append(
                [
                    rule,
                    slots,
                    module.name or module.module_id,
                    module.order_number,
                    module.category_name,
                    io_summary["input_bytes"],
                    io_summary["output_bytes"],
                    io_summary["input_items"],
                    io_summary["output_items"],
                ]
            )

        self.fill_grid(self.composition_table, rows)

    def fill_composition_table_from_project_instance(self, instance: ProjectDeviceInstance):
        rows = []

        for slot in instance.slots:
            if slot.slot_kind == "dap":
                rows.append(
                    [
                        "DAP",
                        slot.slot_number,
                        instance.selected_dap.display_name or instance.selected_dap.name or "DAP",
                        instance.selected_dap.order_number,
                        instance.selected_dap.category_name,
                        "",
                        "",
                        "",
                        "",
                    ]
                )
                continue

            if slot.installed_module is not None:
                module = slot.installed_module
                io_summary = self.get_module_io_summary(module)

                rows.append(
                    [
                        slot.slot_kind,
                        slot.slot_number,
                        module.name or module.module_id,
                        module.order_number,
                        module.category_name,
                        io_summary["input_bytes"],
                        io_summary["output_bytes"],
                        io_summary["input_items"],
                        io_summary["output_items"],
                    ]
                )
                continue

            if slot.allowed_modules:
                rows.append(
                    [
                        "allowed",
                        slot.slot_number,
                        f"Пустой слот, вариантов: {len(slot.allowed_modules)}",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                    ]
                )

        self.fill_grid(self.composition_table, rows)

    def fill_io_table_from_submodules(self, submodules: list[GsdmlSubmodule]):
        rows = []

        for submodule in submodules:
            for item in submodule.input_items:
                rows.append(
                    [
                        item.direction,
                        submodule.name or submodule.submodule_id,
                        item.name,
                        item.data_type,
                        item.bit_length,
                        item.use_as_bits,
                        item.text_id,
                        json.dumps(item.attributes, ensure_ascii=False),
                    ]
                )

            for item in submodule.output_items:
                rows.append(
                    [
                        item.direction,
                        submodule.name or submodule.submodule_id,
                        item.name,
                        item.data_type,
                        item.bit_length,
                        item.use_as_bits,
                        item.text_id,
                        json.dumps(item.attributes, ensure_ascii=False),
                    ]
                )

        self.fill_grid(self.io_data_table, rows)

    def fill_io_table_from_dap(self, dap: GsdmlDeviceAccessPoint):
        submodules = list(dap.submodules)

        for module_ref in dap.module_refs:
            if module_ref.module is not None:
                submodules.extend(module_ref.module.submodules)

        self.fill_io_table_from_submodules(submodules)

    def fill_io_table_from_project_instance(self, instance: ProjectDeviceInstance):
        submodules = []

        for slot in instance.slots:
            if slot.installed_module is not None:
                submodules.extend(slot.installed_module.submodules)

        self.fill_io_table_from_submodules(submodules)

    def on_load_gsd_clicked(self, event):
        with wx.FileDialog(
                self,
                "Загрузить GSDML/XML файл",
                wildcard="GSDML/XML files (*.gsdml;*.xml)|*.gsdml;*.xml|All files (*.*)|*.*",
                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return

            file_path = dialog.GetPath()

        if self.project.contains_gsd_file(file_path):
            wx.MessageBox(
                "Этот GSDML/XML файл уже добавлен в проект.",
                "Файл уже добавлен",
                wx.OK | wx.ICON_INFORMATION,
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

        file_item = self.hardware_catalog.AppendItem(self.hardware_root_item, title)
        self.hardware_catalog.SetItemData(
            file_item,
            {
                "type": "file",
                "file_index": file_index,
            },
        )

        dap_root_item = self.hardware_catalog.AppendItem(file_item, "Варианты устройства / DAP")

        for dap_index, dap in enumerate(device.device_access_points):
            dap_title = dap.display_name or dap.dns_compatible_name or dap.name or dap.dap_id

            dap_item = self.hardware_catalog.AppendItem(dap_root_item, dap_title)
            self.hardware_catalog.SetItemData(
                dap_item,
                {
                    "type": "dap",
                    "file_index": file_index,
                    "dap_index": dap_index,
                },
            )

            self.hardware_catalog.AppendItem(dap_item, f"ID: {dap.dap_id or '-'}")
            self.hardware_catalog.AppendItem(dap_item, f"DNS name: {dap.dns_compatible_name or '-'}")
            self.hardware_catalog.AppendItem(dap_item, f"Category: {dap.category_name or '-'}")
            self.hardware_catalog.AppendItem(dap_item, f"OrderNumber: {dap.order_number or '-'}")
            self.hardware_catalog.AppendItem(dap_item, f"SoftwareRelease: {dap.software_release or '-'}")
            self.hardware_catalog.AppendItem(dap_item, f"PhysicalSlots: {dap.physical_slots or '-'}")
            self.hardware_catalog.AppendItem(dap_item, f"UseableModules: {len(dap.module_refs)}")

            self.append_grouped_modules_for_dap(
                parent_item=dap_item,
                file_index=file_index,
                dap=dap,
                all_modules=device.modules,
            )

        self.hardware_catalog.Expand(self.hardware_root_item)
        self.hardware_catalog.Expand(file_item)
        self.hardware_catalog.Expand(dap_root_item)

    def append_grouped_modules_for_dap(
            self,
            parent_item,
            file_index: int,
            dap: GsdmlDeviceAccessPoint,
            all_modules: list[GsdmlModule],
    ):
        modules_root_item = self.hardware_catalog.AppendItem(parent_item, "Модули этого DAP")

        module_groups: dict[str, list[tuple[int, GsdmlModule]]] = {
            "Входные модули": [],
            "Выходные модули": [],
            "Входные/выходные модули": [],
            "Коммуникационные / интерфейсные": [],
            "Прочие модули": [],
        }

        added_module_ids = set()

        for module_ref in dap.module_refs:
            module = module_ref.module

            if module is None:
                continue

            if module.module_id in added_module_ids:
                continue

            added_module_ids.add(module.module_id)

            module_index = -1
            for index, candidate in enumerate(all_modules):
                if candidate.module_id == module.module_id:
                    module_index = index
                    break

            if module_index < 0:
                continue

            group_name = self.classify_module_for_catalog(module)
            module_groups[group_name].append((module_index, module))

        for group_name, group_modules in module_groups.items():
            if not group_modules:
                continue

            group_item = self.hardware_catalog.AppendItem(modules_root_item, group_name)

            for module_index, module in group_modules:
                module_title = module.name or module.category_name or module.module_id or "Module"

                module_item = self.hardware_catalog.AppendItem(group_item, module_title)
                self.hardware_catalog.SetItemData(
                    module_item,
                    {
                        "type": "module",
                        "file_index": file_index,
                        "module_index": module_index,
                    },
                )

                self.hardware_catalog.AppendItem(module_item, f"ID: {module.module_id or '-'}")
                self.hardware_catalog.AppendItem(module_item, f"OrderNumber: {module.order_number or '-'}")
                self.hardware_catalog.AppendItem(module_item, f"Category: {module.category_name or '-'}")
                self.hardware_catalog.AppendItem(module_item, f"Подмодулей: {len(module.submodules)}")

        self.hardware_catalog.Expand(parent_item)
        self.hardware_catalog.Expand(modules_root_item)

    def show_module_info(self, module: GsdmlModule):
        input_count = 0
        output_count = 0

        for submodule in module.submodules:
            input_count += len(submodule.input_items)
            output_count += len(submodule.output_items)

        self.fill_io_table_from_submodules(module.submodules)
        self.clear_composition_table()

        self.set_overview_text(
            "ModuleItem / модуль:\n\n"
            f"Название: {module.name or '-'}\n"
            f"Описание: {module.info_text or '-'}\n"
            f"Category: {module.category_name or '-'}\n"
            f"SubCategory: {module.subcategory_name or '-'}\n"
            f"ID: {module.module_id or '-'}\n"
            f"ModuleIdentNumber: {module.module_ident_number or '-'}\n"
            f"OrderNumber: {module.order_number or '-'}\n"
            f"Подмодулей: {len(module.submodules)}\n"
            f"Input DataItem: {input_count}\n"
            f"Output DataItem: {output_count}\n"
        )

        self.set_raw_data(self.module_to_dict(module))

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
        device = instance.gsd_file.device

        device_title = instance.instance_name

        if device.vendor_name:
            device_title = f"{device.vendor_name} — {device_title}"

        device_item = self.project_tree.AppendItem(self.project_root_item, device_title)
        self.project_tree.SetItemData(device_item, instance)

        for slot in instance.slots:
            if slot.slot_kind == "dap":
                continue

            if slot.installed_module is None:
                continue

            module = slot.installed_module
            module_title = module.name or module.category_name or module.module_id or "Module"

            slot_item = self.project_tree.AppendItem(
                device_item,
                f"Slot {slot.slot_number}: {module_title}",
            )
            self.project_tree.SetItemData(slot_item, slot)

        self.project_tree.Expand(self.project_root_item)
        self.project_tree.Expand(device_item)

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
            f"GSDML version: {gsd_file.gsdml_version or '-'}\n"
            f"Полная XSD-модель прочитана: {gsd_file.schema_model is not None}\n"
            f"Тип XSD-модели: {type(gsd_file.schema_model).__name__ if gsd_file.schema_model is not None else '-'}\n"
            f"Ошибка XSD-модели: {gsd_file.schema_model_error or '-'}\n\n"

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
                    "schema_model_read": gsd_file.schema_model is not None,
                    "schema_model_type": type(gsd_file.schema_model).__name__
                    if gsd_file.schema_model is not None
                    else "",
                    "schema_model_error": gsd_file.schema_model_error,
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
        self.render_device_graphics(instance)

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

    def module_to_dict(self, module: GsdmlModule | None) -> dict | None:
        if module is None:
            return None

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

    def project_slot_to_dict(self, slot: ProjectSlot) -> dict:
        return {
            "slot_number": slot.slot_number,
            "slot_kind": slot.slot_kind,
            "installed_module": self.module_to_dict(slot.installed_module),
            "allowed_modules": [
                self.module_to_dict(module)
                for module in slot.allowed_modules
            ],
            "source_module_ref": slot.source_module_ref.attributes
            if slot.source_module_ref is not None
            else None,
        }

    def on_hardware_catalog_item_selected(self, event):
        item = event.GetItem()

        if not item.IsOk():
            return

        payload = self.hardware_catalog.GetItemData(item)

        if not isinstance(payload, dict):
            self.set_overview_text(self.hardware_catalog.GetItemText(item))
            self.clear_io_table()
            self.clear_composition_table()
            self.set_raw_data({})
            return

        item_type = payload.get("type")
        file_index = payload.get("file_index")

        if file_index is None:
            self.set_overview_text(self.hardware_catalog.GetItemText(item))
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

        if item_type == "module":
            module_index = payload.get("module_index")

            if module_index is not None and 0 <= module_index < len(device.modules):
                self.show_module_info(device.modules[module_index])
                return

        self.set_overview_text(self.hardware_catalog.GetItemText(item))
        self.clear_io_table()
        self.clear_composition_table()
        self.set_raw_data({})

    def on_project_tree_item_selected(self, event):
        item = event.GetItem()

        if not item.IsOk():
            return

        obj = self.project_tree.GetItemData(item)

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

        self.set_overview_text(self.project_tree.GetItemText(item))
        self.clear_io_table()
        self.clear_composition_table()
        self.set_raw_data({})

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

    def show_graphics_placeholder(self):
        self.graphics_header_sizer.Clear(delete_windows=True)
        self.slots_grid_sizer.Clear(delete_windows=True)

        placeholder = wx.StaticText(
            self.graphics_scroll,
            label=(
                "Здесь будет графическое представление устройства.\n\n"
                "После добавления DAP в проект здесь появятся слоты устройства."
            ),
        )

        self.graphics_header_sizer.Add(placeholder, 0, wx.EXPAND | wx.ALL, 12)

        self.graphics_scroll.Layout()
        self.graphics_scroll.FitInside()


    def render_device_graphics(self, instance: ProjectDeviceInstance):
        self.graphics_scroll.Freeze()

        try:
            self.graphics_header_sizer.Clear(delete_windows=True)
            self.slots_grid_sizer.Clear(delete_windows=True)

            title = wx.StaticText(
                self.graphics_scroll,
                label=(
                    f"{instance.instance_name}\n"
                    f"{instance.selected_dap.display_name or instance.selected_dap.name or ''}"
                ),
            )
            title.Wrap(900)

            self.graphics_header_sizer.Add(title, 0, wx.EXPAND | wx.ALL, 4)

            visible_slots = []

            for slot in instance.slots:
                if slot.slot_kind == "dap":
                    visible_slots.append(slot)
                    continue

                if slot.installed_module is not None:
                    visible_slots.append(slot)
                    continue

                if slot.allowed_modules:
                    visible_slots.append(slot)
                    continue

            if not visible_slots:
                empty_text = wx.StaticText(
                    self.graphics_scroll,
                    label=(
                        "Для выбранного устройства не построены слоты.\n\n"
                        "Возможные причины:\n"
                        "- в GSDML для выбранного DAP нет UseableModules;\n"
                        "- парсер не прочитал ModuleItemRef;\n"
                        "- для этого DAP нет модульной структуры."
                    ),
                )
                self.graphics_header_sizer.Add(empty_text, 0, wx.EXPAND | wx.ALL, 8)
            else:
                for slot in visible_slots:
                    slot_card = SlotCardPanel(
                        self.graphics_scroll,
                        self,
                        slot,
                        instance.selected_dap,
                    )
                    self.slots_grid_sizer.Add(slot_card, 1, wx.EXPAND | wx.ALL, 4)

            self.graphics_scroll.Layout()
            self.graphics_scroll.FitInside()

        finally:
            self.graphics_scroll.Thaw()


    def on_hardware_tree_begin_drag(self, event):
        item = event.GetItem()

        if not item.IsOk():
            return

        payload = self.hardware_catalog.GetItemData(item)

        if not isinstance(payload, dict):
            return

        if payload.get("type") not in ["dap", "module"]:
            return

        data = wx.TextDataObject(json.dumps(payload, ensure_ascii=False))

        drag_source = wx.DropSource(self.hardware_catalog)
        drag_source.SetData(data)
        drag_source.DoDragDrop(wx.Drag_CopyOnly)

    def on_dap_dropped_to_project(self, payload: dict) -> bool:
        file_index = payload.get("file_index")
        dap_index = payload.get("dap_index")

        if file_index is None or dap_index is None:
            return False

        return self.add_dap_to_project(file_index, dap_index)

    def on_module_dropped_to_slot(self, payload: dict, slot: ProjectSlot) -> bool:
        file_index = payload.get("file_index")
        module_index = payload.get("module_index")

        if file_index is None or module_index is None:
            return False

        if file_index < 0 or file_index >= len(self.project.loaded_gsd_files):
            return False

        gsd_file = self.project.loaded_gsd_files[file_index]
        modules = gsd_file.device.modules

        if module_index < 0 or module_index >= len(modules):
            return False

        module = modules[module_index]

        if slot.installed_module is not None or slot.slot_kind == "dap":
            wx.MessageBox(
                "Этот слот уже занят.",
                "Слот занят",
                wx.OK | wx.ICON_WARNING,
            )
            return False

        if not self.is_module_allowed_for_slot(module, slot):
            wx.MessageBox(
                "Этот модуль нельзя установить в выбранный слот.",
                "Модуль не подходит",
                wx.OK | wx.ICON_WARNING,
            )
            return False

        slot.installed_module = module
        slot.slot_kind = "installed"

        instance = self.find_instance_by_slot(slot)

        if instance is not None:
            wx.CallAfter(self.after_module_installed, instance, slot)

        return True

    def after_module_installed(
            self,
            instance: ProjectDeviceInstance,
            slot: ProjectSlot,
    ):
        self.refresh_project_tree()
        self.render_device_graphics(instance)
        self.show_project_slot_info(slot)

    def is_module_allowed_for_slot(
            self,
            module: GsdmlModule,
            slot: ProjectSlot,
    ) -> bool:
        for allowed_module in slot.allowed_modules:
            if allowed_module.module_id == module.module_id:
                return True

        return False

    def find_instance_by_slot(self, target_slot: ProjectSlot) -> ProjectDeviceInstance | None:
        for instance in self.project.device_instances:
            for slot in instance.slots:
                if slot is target_slot:
                    return instance

        return None

    def refresh_project_tree(self):
        self.project_tree.DeleteChildren(self.project_root_item)

        for instance in self.project.device_instances:
            self.add_device_instance_to_project_tree(instance)

        self.project_tree.Expand(self.project_root_item)

    def classify_module_for_catalog(self, module: GsdmlModule) -> str:
        input_items = 0
        output_items = 0

        for submodule in module.submodules:
            input_items += len(submodule.input_items)
            output_items += len(submodule.output_items)

        module_text = " ".join(
            [
                module.name or "",
                module.category_name or "",
                module.subcategory_name or "",
                module.info_text or "",
            ]
        ).lower()

        if input_items > 0 and output_items == 0:
            return "Входные модули"

        if output_items > 0 and input_items == 0:
            return "Выходные модули"

        if input_items > 0 and output_items > 0:
            return "Входные/выходные модули"

        if (
                "ethernet" in module_text
                or "profinet" in module_text
                or "interface" in module_text
                or "communication" in module_text
                or "rj45" in module_text
        ):
            return "Коммуникационные / интерфейсные"

        return "Прочие модули"
