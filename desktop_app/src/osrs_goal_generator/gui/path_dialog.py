from __future__ import annotations

import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..boss_rates import all_boss_names
from ..models import PathDefinition, PlayerProfile, Requirement


class CustomPathDialog(QDialog):
    """Create/edit a multi-requirement custom progression path."""

    def __init__(
        self,
        profile: PlayerProfile,
        path: PathDefinition | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile = profile
        self.existing = path
        self.requirements: list[Requirement] = list(path.requirements) if path else []
        self.setWindowTitle("Edit Custom Path" if path else "Create Custom Path")
        self.resize(720, 520)

        outer = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(path.name if path else "")
        self.name_input.setPlaceholderText("Example: Base 85s, 90 Agility, 500 Vorkath KC")
        form.addRow("Path name", self.name_input)
        outer.addLayout(form)

        builder = QHBoxLayout()
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Skill Level", "skill")
        self.kind_combo.addItem("Boss KC", "boss_kc")
        self.kind_combo.addItem("Total Level", "total_level")
        self.kind_combo.addItem("Base Level", "base_level")

        self.target_combo = QComboBox()
        self.value_spin = QSpinBox()
        self.value_spin.setMinimum(1)
        self.value_spin.setMaximum(100_000)
        self.add_requirement_button = QPushButton("Add Requirement")
        self.add_requirement_button.setObjectName("Primary")

        builder.addWidget(self.kind_combo, 1)
        builder.addWidget(self.target_combo, 2)
        builder.addWidget(self.value_spin, 1)
        builder.addWidget(self.add_requirement_button)
        outer.addLayout(builder)

        self.kind_combo.currentIndexChanged.connect(self._configure_requirement_inputs)
        self.add_requirement_button.clicked.connect(self._add_requirement)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Type", "Target", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        outer.addWidget(self.table, 1)

        remove_row = QHBoxLayout()
        remove_row.addStretch(1)
        remove_button = QPushButton("Remove Selected Requirement")
        remove_button.setObjectName("Secondary")
        remove_button.clicked.connect(self._remove_selected)
        remove_row.addWidget(remove_button)
        outer.addLayout(remove_row)

        note = QLabel(
            "A path can mix multiple skill, boss-KC, total-level, and base-level requirements. "
            "Completed requirements are ignored automatically by the recommendation engine."
        )
        note.setWordWrap(True)
        note.setObjectName("Muted")
        outer.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._configure_requirement_inputs()
        self._render_requirements()

    def _configure_requirement_inputs(self) -> None:
        kind = str(self.kind_combo.currentData())
        self.target_combo.clear()

        if kind == "skill":
            names = sorted(
                name for name in self.profile.skills
                if name != "Overall"
            )
            self.target_combo.addItems(names)
            self.target_combo.setEnabled(True)
            self.value_spin.setRange(2, 99)
            self.value_spin.setValue(90)
        elif kind == "boss_kc":
            self.target_combo.addItems(all_boss_names())
            self.target_combo.setEnabled(True)
            self.value_spin.setRange(1, 100_000)
            self.value_spin.setValue(100)
        elif kind == "total_level":
            self.target_combo.addItem("Overall")
            self.target_combo.setEnabled(False)
            self.value_spin.setRange(1, 2376)
            self.value_spin.setValue(2200)
        else:  # base_level
            self.target_combo.addItem("All Skills")
            self.target_combo.setEnabled(False)
            self.value_spin.setRange(2, 99)
            self.value_spin.setValue(85)

    def _add_requirement(self) -> None:
        kind = str(self.kind_combo.currentData())
        target = self.target_combo.currentText().strip()
        value = int(self.value_spin.value())
        if not target:
            return

        kind_label = {
            "skill": "Skill",
            "boss_kc": "Boss KC",
            "total_level": "Total Level",
            "base_level": "Base Level",
        }[kind]
        label = (
            f"Base {value}s" if kind == "base_level"
            else f"{value} Total Level" if kind == "total_level"
            else f"{target} {value}{' KC' if kind == 'boss_kc' else ''}"
        )

        # Same type+target: keep only the higher target rather than creating
        # contradictory duplicate requirements.
        replaced = False
        for index, existing in enumerate(self.requirements):
            if existing.kind == kind and existing.target == target:
                if float(existing.required_value or 0) >= value:
                    QMessageBox.information(
                        self,
                        "Custom Path",
                        "That requirement already exists at an equal or higher target.",
                    )
                    return
                self.requirements[index] = Requirement(
                    requirement_id=existing.requirement_id,
                    kind=kind,
                    target=target,
                    required_value=value,
                    label=label,
                    weight=existing.weight,
                )
                replaced = True
                break

        if not replaced:
            self.requirements.append(Requirement(
                requirement_id=f"custom:req:{uuid.uuid4().hex[:10]}",
                kind=kind,
                target=target,
                required_value=value,
                label=label,
                weight=1.0 if kind in {"skill", "boss_kc"} else 3.0,
            ))
        self._render_requirements()

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self.requirements):
                del self.requirements[row]
        self._render_requirements()

    def _render_requirements(self) -> None:
        self.table.setRowCount(len(self.requirements))
        for row, requirement in enumerate(self.requirements):
            kind = {
                "skill": "Skill",
                "boss_kc": "Boss KC",
                "total_level": "Total Level",
                "base_level": "Base Level",
            }.get(requirement.kind, requirement.kind.title())
            self.table.setItem(row, 0, QTableWidgetItem(kind))
            self.table.setItem(row, 1, QTableWidgetItem(requirement.target))
            self.table.setItem(row, 2, QTableWidgetItem(str(requirement.required_value or "-")))

    def _validate_and_accept(self) -> None:
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Custom Path", "Give the path a name first.")
            return
        if not self.requirements:
            QMessageBox.warning(self, "Custom Path", "Add at least one requirement.")
            return
        self.accept()

    def path_definition(self) -> PathDefinition:
        path_id = self.existing.path_id if self.existing else f"custom:{uuid.uuid4().hex[:12]}"
        return PathDefinition(
            path_id=path_id,
            name=self.name_input.text().strip(),
            category="custom",
            requirements=tuple(self.requirements),
            description="Custom progression path.",
            is_custom=True,
        )
