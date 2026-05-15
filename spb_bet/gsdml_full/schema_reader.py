import re
from pathlib import Path
from typing import Any

from xsdata.formats.dataclass.parsers import XmlParser
from xsdata.formats.dataclass.parsers.config import ParserConfig


class GsdmlSchemaReader:
    """
    Читает GSDML/XML через заранее сгенерированные xsdata-классы.
    Классы генерируются заранее, а не во время работы программы.
    """

    @classmethod
    def read(cls, file_path: str) -> Any:
        path = Path(file_path)
        version = cls.detect_gsdml_version(path)
        root_class = cls.get_root_class_for_version(version)

        config = ParserConfig(
            fail_on_unknown_properties=True,
            fail_on_unknown_attributes=True,
        )

        parser = XmlParser(config=config)

        return parser.parse(path, clazz=root_class)

    @staticmethod
    def detect_gsdml_version(path: Path) -> str:
        match = re.search(
            r"GSDML-V(?P<version>\d+(?:\.\d+)*)",
            path.name,
            flags=re.IGNORECASE,
        )

        if not match:
            raise ValueError(
                f"Не удалось определить версию GSDML по имени файла: {path.name}"
            )

        return match.group("version")

    @staticmethod
    def get_root_class_for_version(version: str):
        normalized_version = version.strip().upper().replace("V", "")

        if normalized_version == "2.1":
            from spb_bet.gsdml_generated.v21.gsdml_device_profile_v2_1 import (
                Iso15745Profile,
            )

            return Iso15745Profile

        if normalized_version == "2.33":
            from spb_bet.gsdml_generated.v233.gsdml_device_profile_v2_33 import (
                Iso15745Profile,
            )

            return Iso15745Profile

        if normalized_version == "2.35":
            from spb_bet.gsdml_generated.v235.gsdml_device_profile_v2_35 import (
                Iso15745Profile,
            )

            return Iso15745Profile

        raise ValueError(
            f"Для GSDML V{version} нет подключённого XSD-класса. "
            "Нужно сгенерировать классы для этой версии и добавить импорт в GsdmlSchemaReader."
        )