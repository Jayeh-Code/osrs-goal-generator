from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPixmap, QColor, QLinearGradient, QPen
from PySide6.QtWidgets import QFrame
from ..config import ASSETS_DIR


class ScenicFrame(QFrame):
    """Scalable scenery with a readable scrim and a restrained stone bevel."""
    def __init__(self, darkness=0.68, parent=None):
        super().__init__(parent)
        self.darkness = darkness
        self.scene = QPixmap(str(ASSETS_DIR / "ui" / "landscape.png"))
        self._scaled_scene = QPixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.scene.isNull():
            self._scaled_scene = self.scene.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                  Qt.TransformationMode.SmoothTransformation)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b151a"))
        if not self._scaled_scene.isNull():
            painter.drawPixmap((self.width()-self._scaled_scene.width())//2,
                               (self.height()-self._scaled_scene.height())//2, self._scaled_scene)
        shade = QLinearGradient(0, 0, 0, self.height())
        shade.setColorAt(0, QColor(5, 15, 20, int(255*self.darkness)))
        shade.setColorAt(1, QColor(5, 15, 20, 238))
        painter.fillRect(self.rect(), shade)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#414a4b"), 5))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(3, 3, -3, -3), 7, 7)
        painter.setPen(QPen(QColor("#798078"), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(5, 5, -5, -5), 5, 5)
