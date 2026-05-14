import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
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
)

@dataclass
class ProjectGsdFile:
    """
    GSDML/XML файл, загруженный в проект.

    Здесь уже храним не только путь к файлу,
    но и первые данные, прочитанные из XML.
    """

    file_path: str
    file_name: str
    file_extension: str

    is_xml: bool = False
    root_tag: str = ""
    gsdml_version: str = ""

    has_profile_header: bool = False
    has_profile_body: bool = False
    has_device_identity: bool = False

    vendor_id: str = ""
    device_id: str = ""
    vendor_name: str = ""
    device_name: str = ""

class GsdmlReader:
    """
    Минимальный читатель GSDML/XML.

    Пока задача класса:
    - открыть XML;
    - определить корневой тег;
    - найти базовые разделы;
    - вытащить DeviceIdentity;
    - вытащить VendorID / DeviceID / VendorName / DeviceName, если они есть.
    """

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

        gsd_file.gsdml_version = (
            root.attrib.get("Version", "")
            or root.attrib.get("SchemaVersion", "")
            or root.attrib.get("ProfileRevision", "")
        )

        profile_header = GsdmlReader.find_first(root, "ProfileHeader")
        profile_body = GsdmlReader.find_first(root, "ProfileBody")
        device_identity = GsdmlReader.find_first(root, "DeviceIdentity")

        gsd_file.has_profile_header = profile_header is not None
        gsd_file.has_profile_body = profile_body is not None
        gsd_file.has_device_identity = device_identity is not None

        if device_identity is not None:
            gsd_file.vendor_id = GsdmlReader.get_attr_any(
                device_identity,
                ["VendorID", "VendorId", "Vendor_ID"]
            )

            gsd_file.device_id = GsdmlReader.get_attr_any(
                device_identity,
                ["DeviceID", "DeviceId", "Device_ID"]
            )

            gsd_file.vendor_name = GsdmlReader.get_attr_any(
                device_identity,
                ["VendorName", "Vendor_Name", "Manufacturer"]
            )

            gsd_file.device_name = GsdmlReader.get_attr_any(
                device_identity,
                ["DeviceName", "Device_Name", "Name"]
            )

        if not gsd_file.vendor_name:
            gsd_file.vendor_name = GsdmlReader.find_text_or_attr(
                root,
                ["VendorName", "Vendor_Name", "Manufacturer"]
            )

        if not gsd_file.device_name:
            gsd_file.device_name = GsdmlReader.find_text_or_attr(
                root,
                ["DeviceName", "Device_Name", "InfoText", "NameOfStation"]
            )

        if not gsd_file.device_name:
            gsd_file.device_name = path.stem

        return gsd_file

    @staticmethod
    def local_name(tag: str) -> str:
        """
        Убирает namespace из XML-тега.

        Например:
        {http://www.profibus.com/GSDML/2003/11/DeviceProfile}ProfileBody
        станет:
        ProfileBody
        """

        if "}" in tag:
            return tag.split("}", 1)[1]

        return tag

    @staticmethod
    def find_first(root: ET.Element, local_tag_name: str):
        """
        Ищет первый XML-элемент по локальному имени тега.
        Namespace при этом игнорируется.
        """

        for element in root.iter():
            if GsdmlReader.local_name(element.tag) == local_tag_name:
                return element

        return None

    @staticmethod
    def get_attr_any(element: ET.Element, attr_names: list[str]) -> str:
        """
        Возвращает первый найденный атрибут из списка возможных имён.
        """

        for attr_name in attr_names:
            if attr_name in element.attrib:
                return element.attrib[attr_name]

        return ""

    @staticmethod
    def find_text_or_attr(root: ET.Element, names: list[str]) -> str:
        """
        Пытается найти значение по имени тега или атрибута.

        Это нужно потому, что разные производители
        могут хранить близкую информацию в разных местах.
        """

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
    """
    Проект SBP-BET.
    Сейчас проект живёт только в оперативной памяти.
    На диск он пока не сохраняется.
    """

    project_name: str = "Новый проект"
    loaded_gsd_files: list[ProjectGsdFile] = field(default_factory=list)

    def add_gsd_file(self, file_path: str) -> ProjectGsdFile:
        gsd_file = GsdmlReader.read(file_path)

        self.loaded_gsd_files.append(gsd_file)

        return gsd_file

    def contains_gsd_file(self, file_path: str) -> bool:
        """
        Проверяет, был ли уже добавлен такой GSDML/XML файл в проект.
        Сравнение выполняется по полному пути к файлу.
        """

        new_path = Path(file_path).resolve()

        for gsd_file in self.loaded_gsd_files:
            existing_path = Path(gsd_file.file_path).resolve()

            if existing_path == new_path:
                return True

        return False

class MainWindow(QMainWindow):
    """
    Главное окно IDE SBP-BET.
    Пока здесь только интерфейс:
    - меню сверху;
    - дерево проекта слева;
    - основная область по центру;
    - каталог оборудования справа.
    """

    def __init__(self):
        super().__init__()

        self.project = SbpBetProject()

        self.setWindowTitle("SBP-BET")
        self.resize(1400, 800)

        self.create_menu()
        self.create_main_layout()

    def create_menu(self):
        """
        Создаёт верхнее меню программы.
        Пока добавляем меню 'Проект' и пункт 'Загрузить GSD/GSDML'.
        """
        menu_bar = self.menuBar()

        project_menu = menu_bar.addMenu("Проект")

        load_gsd_action = QAction("Загрузить GSD/GSDML", self)
        load_gsd_action.triggered.connect(self.on_load_gsd_clicked)
        project_menu.addAction(load_gsd_action)

        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        project_menu.addAction(exit_action)

    def create_main_layout(self):
        """
        Создаёт основную компоновку окна:
        слева дерево проекта,
        по центру основное окно,
        справа каталог GSD/GSDML файлов.
        """

        main_splitter = QSplitter(Qt.Horizontal)

        # Левая часть — дерево проекта
        self.project_tree = QTreeWidget()
        self.project_tree.setHeaderLabels(["Дерево проекта"])

        root_item = QTreeWidgetItem(["Проект SBP-BET"])
        self.project_tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)

        # Центральная часть — основная область
        self.main_text_area = QTextEdit()
        self.main_text_area.setReadOnly(True)
        self.main_text_area.setText(
            "SBP-BET\n\n"
            "Здесь будет отображаться информация о выбранном устройстве, "
            "модуле или GSD/GSDML файле."
        )

        # Правая часть — каталог оборудования
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_title = QLabel("Загруженные GSDML/XML")
        self.hardware_catalog = QListWidget()
        self.hardware_catalog.itemClicked.connect(self.on_hardware_catalog_item_clicked)

        right_layout.addWidget(right_title)
        right_layout.addWidget(self.hardware_catalog)

        # Добавляем области в splitter
        main_splitter.addWidget(self.project_tree)
        main_splitter.addWidget(self.main_text_area)
        main_splitter.addWidget(right_panel)

        # Относительные размеры областей
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 5)
        main_splitter.setStretchFactor(2, 2)

        self.setCentralWidget(main_splitter)

    def on_load_gsd_clicked(self):
        """
        Открывает окно выбора GSDML/XML файла,
        читает XML и добавляет файл в текущий проект.
        """

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

    def show_gsd_file_info(self, gsd_file: ProjectGsdFile):
        """
        Показывает информацию о выбранном GSDML/XML файле
        в центральном окне.
        """

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

            f"VendorID: {gsd_file.vendor_id or '-'}\n"
            f"DeviceID: {gsd_file.device_id or '-'}\n"
            f"Производитель: {gsd_file.vendor_name or '-'}\n"
            f"Устройство: {gsd_file.device_name or '-'}\n\n"

            f"Всего GSDML/XML файлов в проекте: {len(self.project.loaded_gsd_files)}"
        )

    def on_hardware_catalog_item_clicked(self, item: QListWidgetItem):
        """
        Обрабатывает выбор файла в правом списке.
        По индексу получает ProjectGsdFile из проекта
        и показывает его данные в центральном окне.
        """

        file_index = item.data(Qt.UserRole)

        if file_index is None:
            return

        if file_index < 0 or file_index >= len(self.project.loaded_gsd_files):
            return

        gsd_file = self.project.loaded_gsd_files[file_index]
        self.show_gsd_file_info(gsd_file)

def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()