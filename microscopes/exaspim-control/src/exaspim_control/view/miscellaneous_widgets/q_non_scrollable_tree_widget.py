from PySide6.QtWidgets import QTreeWidget


class QNonScrollableTreeWidget(QTreeWidget):
    """Disable mouse wheel scroll"""

    def wheelEvent(self, event):
        pass
