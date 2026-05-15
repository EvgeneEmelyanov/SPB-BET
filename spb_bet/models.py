from dataclasses import dataclass, field


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
class GsdmlFileNameInfo:
    raw_file_name: str = ""
    is_valid_gsdml_name: bool = False

    gsdml_version: str = ""
    vendor_from_name: str = ""
    device_family_from_name: str = ""
    date_from_name: str = ""


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

    file_name_info: GsdmlFileNameInfo = field(default_factory=GsdmlFileNameInfo)
    device: GsdmlDevice = field(default_factory=GsdmlDevice)

    @property
    def vendor_name(self) -> str:
        return self.device.vendor_name

    @property
    def device_name(self) -> str:
        return self.device.device_name

@dataclass
class ProjectSlot:
    slot_number: str
    slot_kind: str = "empty"  # dap / fixed / used / allowed / empty

    installed_module: GsdmlModule | None = None
    allowed_modules: list[GsdmlModule] = field(default_factory=list)

    source_module_ref: GsdmlModuleRef | None = None

    @property
    def is_occupied(self) -> bool:
        return self.installed_module is not None or self.slot_kind == "dap"

    @property
    def title(self) -> str:
        if self.slot_kind == "dap":
            return f"Slot {self.slot_number}: DAP"

        if self.installed_module is not None:
            module_name = (
                self.installed_module.name
                or self.installed_module.category_name
                or self.installed_module.module_id
                or "Module"
            )
            return f"Slot {self.slot_number}: {module_name}"

        if self.allowed_modules:
            return f"Slot {self.slot_number}: пустой"

        return f"Slot {self.slot_number}: пустой"

@dataclass
class ProjectDeviceInstance:
    instance_name: str
    source_gsd_file_index: int
    gsd_file: ProjectGsdFile
    selected_dap: GsdmlDeviceAccessPoint

    slots: list[ProjectSlot] = field(default_factory=list)