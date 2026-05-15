import json

from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QTreeWidget


class HardwareCatalogTree(QTreeWidget):
    MIME_TYPE = "application/x-spb-bet-hardware-catalog-item"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setHeaderLabels(["Hardware Catalog"])
        self.setDragEnabled(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)

    def startDrag(self, supported_actions):
        item = self.currentItem()

        if item is None:
            return

        payload = item.data(0, Qt.UserRole)

        if not isinstance(payload, dict):
            return

        # Перетаскиваем только DAP.
        # ModuleItem пока остаётся частью состава выбранного DAP.
        if payload.get("type") != "dap":
            return

        mime = QMimeData()
        mime.setData(
            self.MIME_TYPE,
            json.dumps(payload).encode("utf-8"),
        )
        mime.setText(item.text(0))

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class ProjectTree(QTreeWidget):
    def __init__(self, drop_callback, parent=None):
        super().__init__(parent)

        self.drop_callback = drop_callback

        self.setHeaderLabels(["Дерево проекта"])
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DropOnly)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(HardwareCatalogTree.MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(HardwareCatalogTree.MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(HardwareCatalogTree.MIME_TYPE):
            event.ignore()
            return

        raw_payload = bytes(
            event.mimeData().data(HardwareCatalogTree.MIME_TYPE)
        ).decode("utf-8")

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            event.ignore()
            return

        success = self.drop_callback(payload)

        if success:
            event.acceptProposedAction()
        else:
            event.ignore()