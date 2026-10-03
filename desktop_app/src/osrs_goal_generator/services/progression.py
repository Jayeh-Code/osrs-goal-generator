from __future__ import annotations

from dataclasses import dataclass

from ..account_math import lowest_skills
from ..models import (
    PathDefinition,
    PathEvaluation,
    PlayerProfile,
    Requirement,
    RequirementEvaluation,
)


PRIORITY_BONUS = {
    "low": 0.0,
    "medium": 3.0,
    "high": 7.0,
    "critical": 10.0,
}


ALL_SKILL_NAMES = (
    "Attack", "Defence", "Strength", "Hitpoints", "Ranged", "Prayer", "Magic",
    "Cooking", "Woodcutting", "Fletching", "Fishing", "Firemaking", "Crafting",
    "Smithing", "Mining", "Herblore", "Agility", "Thieving", "Slayer", "Farming",
    "Runecraft", "Hunter", "Construction", "Sailing",
)


def _skill_requirements(level: int) -> tuple[Requirement, ...]:
    return tuple(
        Requirement(
            requirement_id=f"skill:{name.lower().replace(' ', '_')}:{level}",
            kind="skill",
            target=name,
            required_value=level,
            label=f"{name} {level}",
            weight=1.0,
        )
        for name in ALL_SKILL_NAMES
    )


BUILT_IN_PATHS: dict[str, PathDefinition] = {
    "base_70s": PathDefinition(
        path_id="base_70s",
        name="Base 70s",
        category="account",
        requirements=_skill_requirements(70),
        description="Raise every skill to at least level 70.",
    ),
    "base_80s": PathDefinition(
        path_id="base_80s",
        name="Base 80s",
        category="account",
        requirements=_skill_requirements(80),
        description="Raise every skill to at least level 80.",
    ),
    "base_90s": PathDefinition(
        path_id="base_90s",
        name="Base 90s",
        category="account",
        requirements=_skill_requirements(90),
        description="Raise every skill to at least level 90.",
    ),
    "total_2000": PathDefinition(
        path_id="total_2000",
        name="2000 Total",
        category="total_level",
        requirements=(Requirement(
            requirement_id="total:2000",
            kind="total_level",
            target="Overall",
            required_value=2000,
            label="2000 Total Level",
            weight=4.0,
        ),),
        description="Reach 2000 total level.",
    ),
    "total_2200": PathDefinition(
        path_id="total_2200",
        name="2200 Total",
        category="total_level",
        requirements=(Requirement(
            requirement_id="total:2200",
            kind="total_level",
            target="Overall",
            required_value=2200,
            label="2200 Total Level",
            weight=5.0,
        ),),
        description="Reach 2200 total level.",
    ),
    "slayer_95": PathDefinition(
        path_id="slayer_95",
        name="95 Slayer",
        category="skill",
        requirements=(Requirement(
            requirement_id="skill:slayer:95",
            kind="skill",
            target="Slayer",
            required_value=95,
            label="Slayer 95",
            weight=4.0,
        ),),
        description="Reach 95 Slayer.",
    ),
    "slayer_99": PathDefinition(
        path_id="slayer_99",
        name="99 Slayer",
        category="skill",
        requirements=(Requirement(
            requirement_id="skill:slayer:99",
            kind="skill",
            target="Slayer",
            required_value=99,
            label="Slayer 99",
            weight=5.0,
        ),),
        description="Reach 99 Slayer.",
    ),
    "max_cape": PathDefinition(
        path_id="max_cape",
        name="Max Cape",
        category="account",
        requirements=_skill_requirements(99),
        description="Reach level 99 in every skill.",
    ),
}


@dataclass(slots=True)
class PathScoringData:
    active_path_targets: set[str]
    blocker_targets: set[str]
    path_target_counts: dict[str, int]
    path_priority_bonus: dict[str, float]


class ProgressionService:
    """Evaluate measurable long-term paths against a live HiScores profile.

    Quests are intentionally excluded from blocker logic because this product
    assumes the player's quest requirements are already satisfied.
    """

    def __init__(self) -> None:
        self._custom_paths: dict[str, PathDefinition] = {}
        self._external_paths: dict[str, PathDefinition] = {}

    def set_custom_paths(self, paths: list[PathDefinition]) -> None:
        self._custom_paths = {path.path_id: path for path in paths}

    def set_external_paths(self, paths: list[PathDefinition]) -> None:
        """Register synthetic paths such as tracked diary tiers."""
        self._external_paths = {path.path_id: path for path in paths}

    def definitions(self) -> list[PathDefinition]:
        paths = list(BUILT_IN_PATHS.values()) + list(self._custom_paths.values())
        return sorted(paths, key=lambda item: (item.is_custom, item.name.lower()))

    def incomplete_definitions(self, profile: PlayerProfile) -> list[PathDefinition]:
        return [
            path
            for path in self.definitions()
            if not self.path_is_complete(path, profile)
        ]

    def definition(self, path_id: str) -> PathDefinition | None:
        return (
            BUILT_IN_PATHS.get(path_id)
            or self._custom_paths.get(path_id)
            or self._external_paths.get(path_id)
        )

    def path_is_complete(self, path: PathDefinition, profile: PlayerProfile) -> bool:
        evaluations = [
            self.evaluate_requirement(requirement, profile)
            for requirement in path.requirements
        ]
        return bool(evaluations) and all(
            item.measurable and item.completed
            for item in evaluations
        )

    def evaluate_requirement(
        self,
        requirement: Requirement,
        profile: PlayerProfile,
    ) -> RequirementEvaluation:
        required = requirement.required_value

        if requirement.kind == "skill":
            skill = profile.skill(requirement.target)
            current = skill.level if skill else 0
            target = float(required or 0)
            progress = 100.0 if target <= 0 else max(0.0, min(100.0, current / target * 100.0))
            return RequirementEvaluation(requirement, current >= target, current, True, progress)

        if requirement.kind == "base_level":
            levels = [
                skill.level
                for name, skill in profile.skills.items()
                if name != "Overall" and skill.level >= 1
            ]
            current = min(levels) if levels else 0
            target = float(required or 0)
            progress = 100.0 if target <= 0 else max(0.0, min(100.0, current / target * 100.0))
            return RequirementEvaluation(requirement, current >= target, current, True, progress)

        if requirement.kind == "total_level":
            current = profile.overall.level if profile.overall else 0
            target = float(required or 0)
            progress = 100.0 if target <= 0 else max(0.0, min(100.0, current / target * 100.0))
            return RequirementEvaluation(requirement, current >= target, current, True, progress)

        if requirement.kind == "boss_kc":
            activity = profile.activity(requirement.target)
            current = max(0, activity.score) if activity else 0
            target = float(required or 0)
            progress = 100.0 if target <= 0 else max(0.0, min(100.0, current / target * 100.0))
            return RequirementEvaluation(requirement, current >= target, current, True, progress)

        return RequirementEvaluation(
            requirement=requirement,
            completed=False,
            current_value=None,
            measurable=False,
            progress_percent=0.0,
        )

    def _targets_for_requirement(
        self,
        item: RequirementEvaluation,
        profile: PlayerProfile,
    ) -> list[str]:
        req = item.requirement
        if req.kind == "skill" or req.kind == "boss_kc":
            return [req.target]
        if req.kind == "base_level":
            target = int(req.required_value or 0)
            return [
                skill.name
                for name, skill in profile.skills.items()
                if name != "Overall" and 1 <= skill.level < target
            ]
        if req.kind == "total_level":
            return [skill.name for skill in lowest_skills(profile, 8)]
        return []

    def _best_action_target(
        self,
        item: RequirementEvaluation,
        profile: PlayerProfile,
    ) -> str | None:
        targets = self._targets_for_requirement(item, profile)
        if not targets:
            return None
        if item.requirement.kind in {"base_level", "total_level"}:
            lows = [skill for skill in lowest_skills(profile, 24) if skill.name in targets]
            if lows:
                return lows[0].name
        return targets[0]

    def evaluate_path(
        self,
        path: PathDefinition,
        profile: PlayerProfile,
        priority: str = "medium",
    ) -> PathEvaluation:
        evaluations = [
            self.evaluate_requirement(requirement, profile)
            for requirement in path.requirements
        ]

        total_weight = sum(max(0.1, e.requirement.weight) for e in evaluations) or 1.0
        completed_weight = sum(
            max(0.1, e.requirement.weight) * (e.progress_percent / 100.0)
            for e in evaluations
        )
        progress = max(0.0, min(100.0, completed_weight / total_weight * 100.0))

        unmet = [e for e in evaluations if not e.completed and e.measurable]
        blocker = max(unmet, key=lambda item: item.progress_percent) if unmet else None

        return PathEvaluation(
            path=path,
            priority=priority,
            requirements=evaluations,
            progress_percent=progress,
            current_blocker=blocker,
        )

    def evaluate_active_paths(
        self,
        profile: PlayerProfile,
        active_specs: list[dict],
    ) -> list[PathEvaluation]:
        result: list[PathEvaluation] = []
        for spec in active_specs:
            path = self.definition(str(spec.get("path_id", "")))
            if not path:
                continue
            priority = str(spec.get("priority", "medium")).lower()
            if priority not in PRIORITY_BONUS:
                priority = "medium"
            evaluation = self.evaluate_path(path, profile, priority)
            if evaluation.current_blocker is None and self.path_is_complete(path, profile):
                continue
            result.append(evaluation)

        # Alpha 5: blocker selection now considers leverage across *all* active
        # paths. A shared requirement wins over an equally-close isolated one.
        target_counts: dict[str, int] = {}
        for evaluation in result:
            seen: set[str] = set()
            for item in evaluation.requirements:
                if item.completed or not item.measurable:
                    continue
                for target in self._targets_for_requirement(item, profile):
                    if target not in seen:
                        target_counts[target] = target_counts.get(target, 0) + 1
                        seen.add(target)

        for evaluation in result:
            unmet = [
                item for item in evaluation.requirements
                if not item.completed and item.measurable
            ]
            if not unmet:
                evaluation.current_blocker = None
                continue

            def blocker_key(item: RequirementEvaluation) -> tuple[int, float, float]:
                targets = self._targets_for_requirement(item, profile)
                leverage = max((target_counts.get(target, 0) for target in targets), default=0)
                # Prefer high leverage first, then near-complete requirements.
                return (leverage, item.progress_percent, item.requirement.weight)

            evaluation.current_blocker = max(unmet, key=blocker_key)

        return result

    def scoring_data(
        self,
        profile: PlayerProfile,
        active_specs: list[dict],
    ) -> PathScoringData:
        active_targets: set[str] = set()
        blocker_targets: set[str] = set()
        counts: dict[str, int] = {}
        priority_bonus: dict[str, float] = {}

        for evaluation in self.evaluate_active_paths(profile, active_specs):
            bonus = PRIORITY_BONUS.get(evaluation.priority, 3.0)
            per_path_targets: set[str] = set()

            for item in evaluation.requirements:
                if item.completed or not item.measurable:
                    continue
                targets = self._targets_for_requirement(item, profile)
                for target in targets:
                    active_targets.add(target)
                    per_path_targets.add(target)
                    priority_bonus[target] = max(priority_bonus.get(target, 0.0), bonus)

            for target in per_path_targets:
                counts[target] = counts.get(target, 0) + 1

            blocker = evaluation.current_blocker
            if blocker:
                target = self._best_action_target(blocker, profile)
                if target:
                    blocker_targets.add(target)

        return PathScoringData(
            active_path_targets=active_targets,
            blocker_targets=blocker_targets,
            path_target_counts=counts,
            path_priority_bonus=priority_bonus,
        )
