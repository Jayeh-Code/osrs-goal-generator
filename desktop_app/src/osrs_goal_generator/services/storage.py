from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..config import STATE_FILE, VERSION
from ..models import Goal, PathDefinition, PlayerProfile


DEFAULT_PREFERENCES: dict[str, Any] = {
    "category_weights": {},
    "blocked_targets": [],
    "recent_targets": [],
    "rerolled_targets": [],
    "favorite_bosses": [],
}

DEFAULT_STATE: dict[str, Any] = {
    "version": VERSION,
    "last_account": None,
    "profiles": {},
}


class StateStore:
    def __init__(self, path: Path = STATE_FILE) -> None:
        self.path = path

    @staticmethod
    def profile_key(rsn: str, account_type: str) -> str:
        return f"{account_type}:{rsn.strip().lower()}"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return deepcopy(DEFAULT_STATE)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return deepcopy(DEFAULT_STATE)

        state = deepcopy(DEFAULT_STATE)
        if isinstance(raw, dict):
            state.update(raw)
        state.setdefault("profiles", {})
        state["version"] = VERSION
        return state

    def save(self, state: dict[str, Any]) -> None:
        state["version"] = VERSION
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        if self.path.exists():
            # Preserve the last readable save before replacing it atomically.
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                temp.unlink(missing_ok=True)
                raise ValueError("Existing save is unreadable; it has not been overwritten.")
            if not isinstance(existing, dict):
                temp.unlink(missing_ok=True)
                raise ValueError("Existing save is invalid; it has not been overwritten.")
            backup = self.path.with_suffix(".backup.json")
            backup_temp = backup.with_suffix(".tmp")
            shutil.copyfile(self.path, backup_temp)
            backup_temp.replace(backup)
        temp.replace(self.path)

    def ensure_profile_entry(
        self,
        state: dict[str, Any],
        rsn: str,
        account_type: str,
    ) -> dict[str, Any]:
        key = self.profile_key(rsn, account_type)
        profiles = state.setdefault("profiles", {})
        entry = profiles.setdefault(
            key,
            {
                "rsn": rsn,
                "account_type": account_type,
                "snapshots": [],
                "active_goal": None,
                "goal_history": [],
                "active_paths": [],
                "custom_paths": [],
                "active_diaries": [],
                "completed_diaries": [],
                "collection_targets": [],
                "preferences": deepcopy(DEFAULT_PREFERENCES),
            },
        )
        entry.setdefault("rsn", rsn)
        entry.setdefault("account_type", account_type)
        entry.setdefault("snapshots", [])
        entry.setdefault("active_goal", None)
        entry.setdefault("goal_history", [])
        entry.setdefault("active_paths", [])
        entry.setdefault("custom_paths", [])
        entry.setdefault("active_diaries", [])
        entry.setdefault("completed_diaries", [])
        entry.setdefault("collection_targets", [])
        prefs = entry.setdefault("preferences", deepcopy(DEFAULT_PREFERENCES))
        for key_name, default_value in DEFAULT_PREFERENCES.items():
            prefs.setdefault(key_name, deepcopy(default_value))

        # One-time Alpha 1 migration: preferences/history used to live globally.
        last = state.get("last_account") or {}
        same_legacy_account = (
            last.get("rsn", "").lower() == rsn.lower()
            and last.get("account_type", "normal") == account_type
        )
        if same_legacy_account and not entry.get("alpha1_migrated"):
            legacy_prefs = state.get("preferences")
            if isinstance(legacy_prefs, dict):
                for pref_name in DEFAULT_PREFERENCES:
                    if pref_name in legacy_prefs:
                        prefs[pref_name] = deepcopy(legacy_prefs[pref_name])
            for raw_goal in state.get("accepted_goals", []):
                if isinstance(raw_goal, dict):
                    entry.setdefault("goal_history", []).append(deepcopy(raw_goal))
            entry["alpha1_migrated"] = True
        return entry

    def latest_profile(
        self,
        state: dict[str, Any],
        rsn: str,
        account_type: str,
    ) -> PlayerProfile | None:
        entry = self.ensure_profile_entry(state, rsn, account_type)
        snapshots = entry.get("snapshots", [])
        if not snapshots:
            return None
        try:
            return PlayerProfile.from_dict(snapshots[-1])
        except (KeyError, TypeError, ValueError):
            return None

    def save_profile(self, state: dict[str, Any], profile: PlayerProfile) -> bool:
        entry = self.ensure_profile_entry(
            state,
            profile.rsn,
            profile.account_type,
        )
        snapshots = entry.setdefault("snapshots", [])
        profile_dict = profile.to_dict()

        # fetched_at always changes, so compare the actual account values.
        def comparable(raw: dict[str, Any]) -> tuple[Any, Any]:
            return raw.get("skills", {}), raw.get("activities", {})

        added = not snapshots or comparable(snapshots[-1]) != comparable(profile_dict)
        if added:
            snapshots.append(profile_dict)
            del snapshots[:-30]

        state["last_account"] = {
            "rsn": profile.rsn,
            "account_type": profile.account_type,
        }
        return added

    def preferences(self, state: dict[str, Any], profile: PlayerProfile) -> dict[str, Any]:
        return self.ensure_profile_entry(
            state,
            profile.rsn,
            profile.account_type,
        )["preferences"]

    def active_goal(self, state: dict[str, Any], profile: PlayerProfile) -> Goal | None:
        raw = self.ensure_profile_entry(
            state,
            profile.rsn,
            profile.account_type,
        ).get("active_goal")
        if not raw:
            return None
        try:
            return Goal.from_dict(raw)
        except (KeyError, TypeError, ValueError):
            return None

    def set_active_goal(self, state: dict[str, Any], profile: PlayerProfile, goal: Goal) -> None:
        entry = self.ensure_profile_entry(
            state,
            profile.rsn,
            profile.account_type,
        )
        existing = entry.get("active_goal")
        if existing:
            old_goal = Goal.from_dict(existing)
            if old_goal.goal_id != goal.goal_id:
                old_goal.status = "abandoned"
                history = entry.setdefault("goal_history", [])
                updated = False
                for index in range(len(history) - 1, -1, -1):
                    if history[index].get("goal_id") == old_goal.goal_id:
                        history[index] = old_goal.to_dict()
                        updated = True
                        break
                if not updated:
                    history.append(old_goal.to_dict())

        entry["active_goal"] = goal.to_dict()
        history = entry.setdefault("goal_history", [])
        history.append(goal.to_dict())
        del history[:-100]

    def update_active_goal(self, state: dict[str, Any], profile: PlayerProfile, goal: Goal) -> None:
        entry = self.ensure_profile_entry(
            state,
            profile.rsn,
            profile.account_type,
        )
        entry["active_goal"] = goal.to_dict()

        history = entry.setdefault("goal_history", [])
        for index in range(len(history) - 1, -1, -1):
            if history[index].get("goal_id") == goal.goal_id:
                history[index] = goal.to_dict()
                break

    def archive_active_goal(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        status: str,
    ) -> Goal | None:
        goal = self.active_goal(state, profile)
        if goal is None:
            return None
        goal.status = status
        entry = self.ensure_profile_entry(
            state,
            profile.rsn,
            profile.account_type,
        )
        history = entry.setdefault("goal_history", [])
        for index in range(len(history) - 1, -1, -1):
            if history[index].get("goal_id") == goal.goal_id:
                history[index] = goal.to_dict()
                break
        entry["active_goal"] = None
        return goal

    def goal_history(self, state: dict[str, Any], profile: PlayerProfile) -> list[Goal]:
        entry = self.ensure_profile_entry(
            state,
            profile.rsn,
            profile.account_type,
        )
        result: list[Goal] = []
        for raw in entry.get("goal_history", []):
            try:
                result.append(Goal.from_dict(raw))
            except (KeyError, TypeError, ValueError):
                continue
        return result

    def record_recent_target(self, state: dict[str, Any], profile: PlayerProfile, target: str) -> None:
        prefs = self.preferences(state, profile)
        recent = prefs.setdefault("recent_targets", [])
        recent.insert(0, target)
        del recent[12:]

    def record_reroll(self, state: dict[str, Any], profile: PlayerProfile, target: str) -> None:
        prefs = self.preferences(state, profile)
        rerolled = prefs.setdefault("rerolled_targets", [])
        rerolled.insert(0, target)
        del rerolled[8:]

    def clear_rerolls(self, state: dict[str, Any], profile: PlayerProfile) -> None:
        self.preferences(state, profile)["rerolled_targets"] = []

    def block_target(self, state: dict[str, Any], profile: PlayerProfile, target: str) -> None:
        prefs = self.preferences(state, profile)
        blocked = prefs.setdefault("blocked_targets", [])
        if target not in blocked:
            blocked.append(target)

    def snapshots(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
    ) -> list[PlayerProfile]:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        result: list[PlayerProfile] = []
        for raw in entry.get("snapshots", []):
            try:
                result.append(PlayerProfile.from_dict(raw))
            except (KeyError, TypeError, ValueError):
                continue
        return result

    def favorite_bosses(self, state: dict[str, Any], profile: PlayerProfile) -> set[str]:
        prefs = self.preferences(state, profile)
        return {str(name) for name in prefs.get("favorite_bosses", []) if name}

    def toggle_favorite_boss(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        boss_name: str,
    ) -> bool:
        prefs = self.preferences(state, profile)
        favorites = prefs.setdefault("favorite_bosses", [])
        if boss_name in favorites:
            favorites.remove(boss_name)
            return False
        favorites.append(boss_name)
        favorites.sort()
        return True

    def active_paths(self, state: dict[str, Any], profile: PlayerProfile) -> list[dict[str, Any]]:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        result: list[dict[str, Any]] = []
        for raw in entry.setdefault("active_paths", []):
            if not isinstance(raw, dict) or not raw.get("path_id"):
                continue
            priority = str(raw.get("priority", "medium")).lower()
            if priority not in {"low", "medium", "high", "critical"}:
                priority = "medium"
            result.append({"path_id": str(raw["path_id"]), "priority": priority})
        return result

    def activate_path(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        path_id: str,
        priority: str = "high",
    ) -> None:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        paths = entry.setdefault("active_paths", [])
        priority = priority.lower()
        if priority not in {"low", "medium", "high", "critical"}:
            priority = "high"
        for spec in paths:
            if isinstance(spec, dict) and spec.get("path_id") == path_id:
                spec["priority"] = priority
                return
        paths.append({"path_id": path_id, "priority": priority})

    def deactivate_path(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        path_id: str,
    ) -> None:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        paths = entry.setdefault("active_paths", [])
        entry["active_paths"] = [
            spec for spec in paths
            if not (isinstance(spec, dict) and spec.get("path_id") == path_id)
        ]

    def update_path_priority(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        path_id: str,
        priority: str,
    ) -> None:
        self.activate_path(state, profile, path_id, priority)

    def custom_paths(self, state: dict[str, Any], profile: PlayerProfile) -> list[PathDefinition]:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        result: list[PathDefinition] = []
        for raw in entry.setdefault("custom_paths", []):
            if not isinstance(raw, dict):
                continue
            try:
                path = PathDefinition.from_dict(raw)
            except (TypeError, ValueError, KeyError):
                continue
            if path.path_id:
                result.append(path)
        return result

    def save_custom_path(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        path: PathDefinition,
    ) -> None:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        paths = entry.setdefault("custom_paths", [])
        raw = path.to_dict()
        for index, existing in enumerate(paths):
            if isinstance(existing, dict) and existing.get("path_id") == path.path_id:
                paths[index] = raw
                return
        paths.append(raw)

    def delete_custom_path(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        path_id: str,
    ) -> None:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        entry["custom_paths"] = [
            raw for raw in entry.setdefault("custom_paths", [])
            if not (isinstance(raw, dict) and raw.get("path_id") == path_id)
        ]
        self.deactivate_path(state, profile, path_id)


    def collection_targets(self, state: dict[str, Any], profile: PlayerProfile) -> list[dict[str, Any]]:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        result: list[dict[str, Any]] = []
        for raw in entry.setdefault("collection_targets", []):
            if not isinstance(raw, dict) or not raw.get("target_id") or not raw.get("name"):
                continue
            current = max(0, int(raw.get("current", 0)))
            total = max(1, int(raw.get("total", 1)))
            result.append({
                "target_id": str(raw["target_id"]),
                "name": str(raw["name"]),
                "category": str(raw.get("category", "Other")),
                "current": min(current, total),
                "total": total,
                "notes": str(raw.get("notes", "")),
            })
        return result

    def save_collection_target(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        target: dict[str, Any],
    ) -> None:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        targets = entry.setdefault("collection_targets", [])
        payload = {
            "target_id": str(target.get("target_id", "")).strip(),
            "name": str(target.get("name", "")).strip(),
            "category": str(target.get("category", "Other")).strip() or "Other",
            "current": max(0, int(target.get("current", 0))),
            "total": max(1, int(target.get("total", 1))),
            "notes": str(target.get("notes", "")).strip(),
        }
        payload["current"] = min(payload["current"], payload["total"])
        if not payload["target_id"] or not payload["name"]:
            raise ValueError("Collection targets require an id and name.")
        for index, raw in enumerate(targets):
            if isinstance(raw, dict) and raw.get("target_id") == payload["target_id"]:
                targets[index] = payload
                break
        else:
            targets.append(payload)

    def delete_collection_target(
        self, state: dict[str, Any], profile: PlayerProfile, target_id: str
    ) -> None:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        entry["collection_targets"] = [
            raw for raw in entry.setdefault("collection_targets", [])
            if not isinstance(raw, dict) or raw.get("target_id") != target_id
        ]

    def active_diaries(self, state: dict[str, Any], profile: PlayerProfile) -> list[dict[str, Any]]:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        result: list[dict[str, Any]] = []
        for raw in entry.setdefault("active_diaries", []):
            if not isinstance(raw, dict) or not raw.get("diary_id"):
                continue
            priority = str(raw.get("priority", "medium")).lower()
            if priority not in {"low", "medium", "high", "critical"}:
                priority = "medium"
            result.append({"diary_id": str(raw["diary_id"]), "priority": priority})
        return result

    def track_diary(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        diary_id: str,
        priority: str = "medium",
    ) -> None:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        tracked = entry.setdefault("active_diaries", [])
        priority = priority.lower()
        if priority not in {"low", "medium", "high", "critical"}:
            priority = "medium"
        for spec in tracked:
            if isinstance(spec, dict) and spec.get("diary_id") == diary_id:
                spec["priority"] = priority
                return
        tracked.append({"diary_id": diary_id, "priority": priority})

    def untrack_diary(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        diary_id: str,
    ) -> None:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        entry["active_diaries"] = [
            spec for spec in entry.setdefault("active_diaries", [])
            if not (isinstance(spec, dict) and spec.get("diary_id") == diary_id)
        ]

    def completed_diaries(self, state: dict[str, Any], profile: PlayerProfile) -> set[str]:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        return {str(value) for value in entry.setdefault("completed_diaries", []) if value}

    def mark_diary_complete(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        diary_id: str,
    ) -> None:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        completed = entry.setdefault("completed_diaries", [])
        if diary_id not in completed:
            completed.append(diary_id)
            completed.sort()
        self.untrack_diary(state, profile, diary_id)

    def restore_diary(
        self,
        state: dict[str, Any],
        profile: PlayerProfile,
        diary_id: str,
    ) -> None:
        entry = self.ensure_profile_entry(state, profile.rsn, profile.account_type)
        completed = entry.setdefault("completed_diaries", [])
        if diary_id in completed:
            completed.remove(diary_id)

