from dataclasses import dataclass, field
from pathlib import Path

from spb_bet.gsdml_reader import GsdmlReader
from spb_bet.models import (
    GsdmlDeviceAccessPoint,
    GsdmlModule,
    GsdmlModuleRef,
    ProjectDeviceInstance,
    ProjectGsdFile,
    ProjectSlot,
)


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

        instance.slots = self.build_slots_for_dap(selected_dap)

        self.device_instances.append(instance)

        return instance

    def build_slots_for_dap(self, dap: GsdmlDeviceAccessPoint) -> list[ProjectSlot]:
        """
        Строит слоты устройства по выбранному DAP.

        Логика:
        - сам DAP ставится в слоты из dap.fixed_in_slots;
        - если dap.fixed_in_slots не указан, используем slot 0;
        - FixedInSlots / UsedInSlots у ModuleItemRef считаются уже занятыми;
        - AllowedInSlots у ModuleItemRef считаются пустыми слотами с доступными вариантами.
        """

        slots_by_number: dict[str, ProjectSlot] = {}

        dap_slots = self.expand_slot_expression(dap.fixed_in_slots)

        if not dap_slots:
            dap_slots = ["0"]

        for dap_slot_number in dap_slots:
            slots_by_number[dap_slot_number] = ProjectSlot(
                slot_number=dap_slot_number,
                slot_kind="dap",
            )

        for module_ref in dap.module_refs:
            fixed_slots = self.expand_slot_expression(module_ref.fixed_in_slots)
            used_slots = self.expand_slot_expression(module_ref.used_in_slots)
            allowed_slots = self.expand_slot_expression(module_ref.allowed_in_slots)

            for slot_number in fixed_slots:
                self.set_installed_slot(
                    slots_by_number=slots_by_number,
                    slot_number=slot_number,
                    slot_kind="fixed",
                    module_ref=module_ref,
                )

            for slot_number in used_slots:
                self.set_installed_slot(
                    slots_by_number=slots_by_number,
                    slot_number=slot_number,
                    slot_kind="used",
                    module_ref=module_ref,
                )

            for slot_number in allowed_slots:
                self.add_allowed_module_to_slot(
                    slots_by_number=slots_by_number,
                    slot_number=slot_number,
                    module_ref=module_ref,
                )

        return sorted(
            slots_by_number.values(),
            key=lambda slot: self.slot_sort_key(slot.slot_number),
        )

    def set_installed_slot(
        self,
        slots_by_number: dict[str, ProjectSlot],
        slot_number: str,
        slot_kind: str,
        module_ref: GsdmlModuleRef,
    ):
        slot = slots_by_number.get(slot_number)

        if slot is None:
            slot = ProjectSlot(slot_number=slot_number)
            slots_by_number[slot_number] = slot

        slot.slot_kind = slot_kind
        slot.installed_module = module_ref.module
        slot.source_module_ref = module_ref

    def add_allowed_module_to_slot(
            self,
            slots_by_number: dict[str, ProjectSlot],
            slot_number: str,
            module_ref: GsdmlModuleRef,
    ):
        slot = slots_by_number.get(slot_number)

        if slot is None:
            slot = ProjectSlot(
                slot_number=slot_number,
                slot_kind="allowed",
            )
            slots_by_number[slot_number] = slot

        if slot.slot_kind in ["dap", "fixed", "used"]:
            return

        if slot.slot_kind == "empty":
            slot.slot_kind = "allowed"

        if module_ref.module is not None:
            if not self.module_already_in_list(module_ref.module, slot.allowed_modules):
                slot.allowed_modules.append(module_ref.module)

    def module_already_in_list(
        self,
        module: GsdmlModule,
        modules: list[GsdmlModule],
    ) -> bool:
        for existing_module in modules:
            if existing_module.module_id == module.module_id:
                return True

        return False

    def expand_slot_expression(self, expression: str) -> list[str]:
        """
        Преобразует выражения слотов из GSDML в список номеров.

        Примеры:
        "2"       -> ["2"]
        "12..15"  -> ["12", "13", "14", "15"]
        "6 7"     -> ["6", "7"]
        "6.7"     -> ["6", "7"]
        "6,7"     -> ["6", "7"]
        """

        if not expression:
            return []

        result: list[str] = []
        original_parts = expression.replace(",", " ").replace(";", " ").split()

        for part in original_parts:
            if ".." in part:
                range_parts = part.split("..", 1)

                if len(range_parts) != 2:
                    continue

                try:
                    start = int(range_parts[0])
                    end = int(range_parts[1])
                except ValueError:
                    continue

                if start <= end:
                    for value in range(start, end + 1):
                        result.append(str(value))
                else:
                    for value in range(start, end - 1, -1):
                        result.append(str(value))

                continue

            subparts = part.replace(",", " ").replace(";", " ").replace(".", " ").split()

            for subpart in subparts:
                if subpart:
                    result.append(subpart)

        return self.unique_keep_order(result)

    def unique_keep_order(self, values: list[str]) -> list[str]:
        seen = set()
        result = []

        for value in values:
            if value in seen:
                continue

            seen.add(value)
            result.append(value)

        return result

    def slot_sort_key(self, slot_number: str):
        try:
            return int(slot_number)
        except ValueError:
            return slot_number