from dataclasses import dataclass, field
from pathlib import Path

from spb_bet.gsdml_reader import GsdmlReader
from spb_bet.models import (
    GsdmlDeviceAccessPoint,
    ProjectDeviceInstance,
    ProjectGsdFile,
)


@dataclass
class SpbBetProject:
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