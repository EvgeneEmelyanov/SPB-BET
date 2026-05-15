import xml.etree.ElementTree as ET
from pathlib import Path

from spb_bet.models import (
    GsdmlCategory,
    GsdmlDevice,
    GsdmlDeviceAccessPoint,
    GsdmlFileNameInfo,
    GsdmlGraphic,
    GsdmlIoDataItem,
    GsdmlModule,
    GsdmlModuleRef,
    GsdmlSubmodule,
    ProjectGsdFile,
)


class GsdmlReader:
    @staticmethod
    def read(file_path: str) -> ProjectGsdFile:
        path = Path(file_path)

        gsd_file = ProjectGsdFile(
            file_path=str(path),
            file_name=path.name,
            file_extension=path.suffix.lower(),
        )

        gsd_file.file_name_info = GsdmlReader.read_file_name_info(path.name)

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
    def read_file_name_info(file_name: str) -> GsdmlFileNameInfo:
        result = GsdmlFileNameInfo(raw_file_name=file_name)

        path = Path(file_name)
        stem = path.stem
        parts = stem.split("-")

        if len(parts) < 5:
            return result

        if parts[0].upper() != "GSDML":
            return result

        result.is_valid_gsdml_name = True
        result.gsdml_version = parts[1]
        result.vendor_from_name = parts[2]
        result.date_from_name = parts[-1]
        result.device_family_from_name = "-".join(parts[3:-1])

        return result

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
            ["VendorID", "VendorId", "Vendor_ID"],
        )

        device.device_id = GsdmlReader.get_attr_any(
            device_identity,
            ["DeviceID", "DeviceId", "Device_ID"],
        )

        vendor_name_element = GsdmlReader.find_first_inside(device_identity, "VendorName")
        info_text_element = GsdmlReader.find_first_inside(device_identity, "InfoText")

        if vendor_name_element is not None:
            device.vendor_name = (
                vendor_name_element.attrib.get("Value", "")
                or GsdmlReader.resolve_text(
                    device.texts,
                    vendor_name_element.attrib.get("TextId", ""),
                )
            )

        if info_text_element is not None:
            text_id = info_text_element.attrib.get("TextId", "")
            device.info_text = GsdmlReader.resolve_text(device.texts, text_id)
            device.device_name = device.info_text

        if not device.vendor_name:
            device.vendor_name = GsdmlReader.find_text_or_attr(
                root,
                ["VendorName", "Vendor_Name", "Manufacturer"],
            )

        if not device.device_name:
            device.device_name = GsdmlReader.find_text_or_attr(
                root,
                ["DeviceName", "Device_Name", "InfoText", "NameOfStation"],
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
                family_element.attrib.get("TextId", ""),
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