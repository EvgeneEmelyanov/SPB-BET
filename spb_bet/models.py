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