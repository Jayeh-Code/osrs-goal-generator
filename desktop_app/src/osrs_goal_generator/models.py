from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Skill:
    name: str
    rank: int
    level: int
    xp: int


@dataclass(slots=True)
class Activity:
    name: str
    rank: int
    score: int


@dataclass(slots=True)
class PlayerProfile:
    rsn: str
    account_type: str
    fetched_at: str
    skills: dict[str, Skill] = field(default_factory=dict)
    activities: dict[str, Activity] = field(default_factory=dict)

    @property
    def overall(self) -> Skill | None:
        return self.skills.get("Overall")

    def skill(self, name: str) -> Skill | None:
        return self.skills.get(name)

    def activity(self, name: str) -> Activity | None:
        return self.activities.get(name)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PlayerProfile":
        skills = {
            name: Skill(**value)
            for name, value in raw.get("skills", {}).items()
        }
        activities = {
            name: Activity(**value)
            for name, value in raw.get("activities", {}).items()
        }
        return cls(
            rsn=raw["rsn"],
            account_type=raw.get("account_type", "normal"),
            fetched_at=raw.get(
                "fetched_at",
                datetime.now().isoformat(timespec="seconds"),
            ),
            skills=skills,
            activities=activities,
        )


@dataclass(slots=True, frozen=True)
class GoalFilters:
    category: str = "surprise me"
    difficulty: str = "moderate"
    session_minutes: int = 60


@dataclass(slots=True)
class ScoreBreakdown:
    base: float = 50.0
    progression: float = 0.0
    active_path: float = 0.0
    blocker: float = 0.0
    proximity: float = 0.0
    session_fit: float = 0.0
    preference: float = 0.0
    variety: float = 0.0
    cross_path: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.base
            + self.progression
            + self.active_path
            + self.blocker
            + self.proximity
            + self.session_fit
            + self.preference
            + self.variety
            + self.cross_path
        )


@dataclass(slots=True)
class GoalCandidate:
    category: str
    subtype: str
    target_name: str
    title: str
    objective: str
    reasons: list[str]
    start_value: int | float | None = None
    target_value: int | float | None = None
    estimated_minutes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    score: ScoreBreakdown = field(default_factory=ScoreBreakdown)


@dataclass(slots=True)
class Goal:
    goal_id: str
    generated_at: str
    category: str
    subtype: str
    target_name: str
    title: str
    objective: str
    reasons: list[str]
    bonus: str | None = None
    start_value: int | float | None = None
    target_value: int | float | None = None
    estimated_minutes: int | None = None
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "generated"
    accepted_at: str | None = None
    completed_at: str | None = None
    current_value: int | float | None = None
    progress_percent: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Goal":
        # Alpha 1 did not persist target_name, so keep older save files readable.
        target_name = raw.get("target_name") or raw.get("title", "").replace(" Progress", "")
        return cls(
            goal_id=raw.get("goal_id", "legacy"),
            generated_at=raw.get(
                "generated_at",
                datetime.now().isoformat(timespec="seconds"),
            ),
            category=raw.get("category", "unknown"),
            subtype=raw.get("subtype", "unknown"),
            target_name=target_name,
            title=raw.get("title", "Saved Goal"),
            objective=raw.get("objective", ""),
            reasons=list(raw.get("reasons", [])),
            bonus=raw.get("bonus"),
            start_value=raw.get("start_value"),
            target_value=raw.get("target_value"),
            estimated_minutes=raw.get("estimated_minutes"),
            score=float(raw.get("score", 0.0)),
            score_breakdown=dict(raw.get("score_breakdown", {})),
            metadata=dict(raw.get("metadata", {})),
            status=raw.get("status", "generated"),
            accepted_at=raw.get("accepted_at"),
            completed_at=raw.get("completed_at"),
            current_value=raw.get("current_value"),
            progress_percent=float(raw.get("progress_percent", 0.0)),
        )


@dataclass(slots=True, frozen=True)
class Requirement:
    requirement_id: str
    kind: str
    target: str
    required_value: int | float | str | None = None
    label: str = ""
    weight: float = 1.0
    manual: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Requirement":
        return cls(
            requirement_id=str(raw.get("requirement_id", "custom:unknown")),
            kind=str(raw.get("kind", "manual")),
            target=str(raw.get("target", "Unknown")),
            required_value=raw.get("required_value"),
            label=str(raw.get("label", "")),
            weight=float(raw.get("weight", 1.0)),
            manual=bool(raw.get("manual", False)),
            note=str(raw.get("note", "")),
        )


@dataclass(slots=True, frozen=True)
class DiaryDefinition:
    diary_id: str
    name: str
    tier: str
    requirements: tuple[Requirement, ...] = ()
    source_url: str = ""
    description: str = ""
    manual_requirement_count: int = 0


@dataclass(slots=True, frozen=True)
class PathDefinition:
    path_id: str
    name: str
    category: str
    requirements: tuple[Requirement, ...] = ()
    description: str = ""
    source_url: str = ""
    is_custom: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_id": self.path_id,
            "name": self.name,
            "category": self.category,
            "requirements": [item.to_dict() for item in self.requirements],
            "description": self.description,
            "source_url": self.source_url,
            "is_custom": self.is_custom,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PathDefinition":
        requirements = tuple(
            Requirement.from_dict(item)
            for item in raw.get("requirements", [])
            if isinstance(item, dict)
        )
        return cls(
            path_id=str(raw.get("path_id", "custom:unknown")),
            name=str(raw.get("name", "Custom Path")),
            category=str(raw.get("category", "custom")),
            requirements=requirements,
            description=str(raw.get("description", "")),
            source_url=str(raw.get("source_url", "")),
            is_custom=bool(raw.get("is_custom", True)),
        )


@dataclass(slots=True)
class RequirementEvaluation:
    requirement: Requirement
    completed: bool
    current_value: int | float | str | None
    measurable: bool
    progress_percent: float


@dataclass(slots=True)
class PathEvaluation:
    path: PathDefinition
    priority: str
    requirements: list[RequirementEvaluation]
    progress_percent: float
    current_blocker: RequirementEvaluation | None = None
