from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..models import Goal, PlayerProfile
from .runelite_sync import RuneLiteSyncSnapshot
import uuid


@dataclass(slots=True)
class GoalProgress:
    verifiable: bool
    completed: bool
    current_value: int | float | None
    progress_percent: float
    label: str
    source: str = "HiScores"


class GoalProgressService:
    """Read account snapshots and verify measurable goals."""

    @staticmethod
    def is_live(snapshot: RuneLiteSyncSnapshot | None, profile: PlayerProfile) -> bool:
        return bool(snapshot and snapshot.matches(profile) and snapshot.is_fresh()
                    and snapshot.game_state == "LOGGED_IN")

    def collection_goal(self, profile: PlayerProfile, snapshot: RuneLiteSyncSnapshot | None,
                        page_name: str) -> Goal:
        if not self.is_live(snapshot, profile):
            raise ValueError("Connect RuneLite on this account and open the Collection Log page first.")
        page = snapshot.collection_pages.get(page_name)
        if not page or not page.missing_items:
            raise ValueError("This page has no observed missing items to track.")
        return Goal(
            goal_id=uuid.uuid4().hex[:12], generated_at=datetime.now().isoformat(timespec="seconds"),
            category="collection", subtype="collection_slot", target_name=page_name,
            title=f"Collection Hunt: {page_name}",
            objective=f"Obtain one of the observed missing items from {page_name}.",
            reasons=["Tracks exact item IDs from this observed page.",
                     "Reopen this Collection Log page after an unlock to verify it."],
            start_value=0, target_value=1,
            metadata={"collection_item_ids": [item.item_id for item in page.missing_items]},
        )

    def evaluate(self, goal: Goal, profile: PlayerProfile,
                 snapshot: RuneLiteSyncSnapshot | None = None) -> GoalProgress:
        source = "HiScores"
        live = self.is_live(snapshot, profile)
        current = self._current_value(goal, profile)
        if goal.subtype == "collection_slot":
            page = snapshot.collection_pages.get(goal.target_name) if live else None
            tracked = set(goal.metadata.get("collection_item_ids", []))
            if not page or not tracked or not tracked.issubset({i.item_id for i in page.items}):
                return GoalProgress(False, False, goal.current_value, goal.progress_percent,
                                    "Open this page in RuneLite to verify progress", "Waiting for RuneLite")
            current = sum(item.obtained for item in page.items if item.item_id in tracked)
            source = "RuneLite observed page"
        elif goal.subtype == "boss_kc":
            if live and goal.target_name in snapshot.boss_counts:
                current = max(current or 0, snapshot.boss_counts[goal.target_name])
                source = "RuneLite live"
            if goal.current_value is not None and (current is None or goal.current_value > current or (not live and goal.current_value == current)):
                current = goal.current_value
                source = "Last verified progress"
        elif goal.subtype in {"skill_xp", "skill_level"}:
            if live and goal.target_name in snapshot.skills:
                current = snapshot.skills[goal.target_name]["xp"]
                source = "RuneLite live"
            # A saved, verified XP checkpoint must not roll backwards when public
            # HiScores lag behind or the desktop restarts without the companion.
            if goal.current_value is not None and (current is None or goal.current_value > current or (not live and goal.current_value == current)):
                current = goal.current_value
                source = "Last verified progress"
        
        if current is None or goal.start_value is None or goal.target_value is None:
            return GoalProgress(
                verifiable=False,
                completed=False,
                current_value=current,
                progress_percent=0.0,
                label="Manual completion",
            )

        start = float(goal.start_value)
        target = float(goal.target_value)
        current_f = float(current)
        span = target - start

        if span <= 0:
            percent = 100.0 if current_f >= target else 0.0
        else:
            percent = max(0.0, min(100.0, ((current_f - start) / span) * 100.0))

        completed = current_f >= target
        return GoalProgress(
            verifiable=True,
            completed=completed,
            current_value=current,
            progress_percent=percent,
            label=self._progress_label(goal, current),
            source=source,
        )

    def apply(self, goal: Goal, profile: PlayerProfile,
              snapshot: RuneLiteSyncSnapshot | None = None) -> GoalProgress:
        result = self.evaluate(goal, profile, snapshot)
        if result.verifiable:
            goal.current_value = result.current_value
            goal.progress_percent = result.progress_percent
        if result.completed and goal.status == "accepted":
            goal.status = "completed"
            goal.completed_at = datetime.now().isoformat(timespec="seconds")
        return result

    def _current_value(self, goal: Goal, profile: PlayerProfile) -> int | float | None:
        if goal.subtype in {"skill_xp", "skill_level"}:
            skill = profile.skill(goal.target_name)
            return skill.xp if skill else None

        if goal.subtype == "boss_kc":
            activity = profile.activity(goal.target_name)
            # Jagex reports unranked boss activities as -1. For a supported boss,
            # that means the visible starting KC is zero, not "unverifiable".
            return max(0, activity.score) if activity else 0

        if goal.subtype in {"clue_count", "collection_logged"}:
            activity = profile.activity(goal.target_name)
            return activity.score if activity and activity.score >= 0 else None

        return None

    @staticmethod
    def _progress_label(goal: Goal, current: int | float) -> str:
        if goal.subtype in {"skill_xp", "skill_level"}:
            gained = max(0, int(current - (goal.start_value or 0)))
            remaining = max(0, int((goal.target_value or current) - current))
            return f"+{gained:,} XP toward goal | {remaining:,} XP remaining"
        if goal.subtype == "collection_slot":
            return f"{min(int(current), int(goal.target_value or 1))} / {int(goal.target_value or 1)} observed unlocks"
        if goal.subtype == "boss_kc":
            return f"{int(current):,} KC / completions"
        if goal.subtype == "clue_count":
            return f"{int(current):,} clues"
        if goal.subtype == "collection_logged":
            return f"{int(current):,} slots logged"
        return str(current)


def compare_profiles(previous: PlayerProfile | None, current: PlayerProfile) -> dict[str, list[dict[str, Any]]]:
    if previous is None:
        return {"skills": [], "activities": []}

    skill_changes: list[dict[str, Any]] = []
    for name, skill in current.skills.items():
        if name == "Overall":
            continue
        old = previous.skill(name)
        if old is None:
            continue
        xp_delta = skill.xp - old.xp
        level_delta = skill.level - old.level
        if xp_delta > 0 or level_delta > 0:
            skill_changes.append({
                "name": name,
                "xp_delta": max(0, xp_delta),
                "old_level": old.level,
                "new_level": skill.level,
            })

    activity_changes: list[dict[str, Any]] = []
    for name, activity in current.activities.items():
        old = previous.activity(name)
        if old is None:
            continue
        old_score = max(0, old.score)
        new_score = max(0, activity.score)
        delta = new_score - old_score
        if delta > 0:
            activity_changes.append({
                "name": name,
                "delta": delta,
                "old": old_score,
                "new": new_score,
            })

    skill_changes.sort(key=lambda item: item["xp_delta"], reverse=True)
    activity_changes.sort(key=lambda item: item["delta"], reverse=True)
    return {"skills": skill_changes, "activities": activity_changes}
