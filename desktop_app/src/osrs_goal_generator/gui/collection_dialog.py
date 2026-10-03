from __future__ import annotations

import uuid

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)


COLLECTION_CATEGORIES = [
    "Bosses",
    "Raids",
    "Clues",
    "Minigames",
    "Slayer",
    "Other",
]


class CollectionTargetDialog(QDialog):
    def __init__(self, target: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._target = dict(target or {})
        self.setWindowTitle("Collection Target")
        self.setMinimumWidth(430)

        outer = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit(str(self._target.get("name", "")))
        self.name_input.setPlaceholderText("e.g. Vorkath uniques")
        form.addRow("Target name", self.name_input)

        self.category_combo = QComboBox()
        self.category_combo.addItems(COLLECTION_CATEGORIES)
        category = str(self._target.get("category", "Bosses"))
        if category not in COLLECTION_CATEGORIES:
            self.category_combo.addItem(category)
        self.category_combo.setCurrentText(category)
        form.addRow("Category", self.category_combo)

        self.current_spin = QSpinBox()
        self.current_spin.setRange(0, 10000)
        self.current_spin.setValue(int(self._target.get("current", 0)))
        form.addRow("Slots obtained", self.current_spin)

        self.total_spin = QSpinBox()
        self.total_spin.setRange(1, 10000)
        self.total_spin.setValue(max(1, int(self._target.get("total", 1))))
        form.addRow("Total slots", self.total_spin)

        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Optional notes, missing drops, method, etc.")
        self.notes_input.setMaximumHeight(100)
        self.notes_input.setPlainText(str(self._target.get("notes", "")))
        form.addRow("Notes", self.notes_input)

        outer.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("Primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setObjectName("Secondary")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        if not self.name_input.text().strip():
            self.name_input.setFocus()
            return
        if self.current_spin.value() > self.total_spin.value():
            self.current_spin.setValue(self.total_spin.value())
        self.accept()

    def target(self) -> dict:
        return {
            "target_id": str(self._target.get("target_id") or uuid.uuid4().hex[:12]),
            "name": self.name_input.text().strip(),
            "category": self.category_combo.currentText(),
            "current": self.current_spin.value(),
            "total": self.total_spin.value(),
            "notes": self.notes_input.toPlainText().strip(),
        }
