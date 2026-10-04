"""Copy validated legacy saves without modifying the original or replacing current data."""
import json
from pathlib import Path


def read_save(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("profiles"), dict):
        raise ValueError("This file is not an OSRS Goal Generator save (profiles are missing).")
    for profile in raw["profiles"].values():
        if not isinstance(profile, dict):
            raise ValueError("This save contains an invalid account entry.")
        def require(value, kind, field):
            if not isinstance(value, kind):
                raise ValueError(f"Invalid saved {field}. Restore a backup instead of replacing this save.")
        for field in ("snapshots", "goal_history", "active_paths", "custom_paths",
                      "active_diaries", "completed_diaries", "collection_targets"):
            if field in profile:
                require(profile[field], list, field)
        preferences = profile.get("preferences", {})
        require(preferences, dict, "preferences")
        for field in ("blocked_targets", "recent_targets", "rerolled_targets", "favorite_bosses"):
            if field in preferences:
                require(preferences[field], list, field)
        require(preferences.get("category_weights", {}), dict, "category weights")
        for field in ("active_goal",):
            if profile.get(field) is not None:
                require(profile[field], dict, field)
        for target in profile.get("collection_targets", []):
            require(target, dict, "collection target")
            for field in ("current", "total"):
                if field in target:
                    try:
                        int(target[field])
                    except (ValueError, TypeError, OverflowError) as exc:
                        raise ValueError(f"Invalid collection {field} in save.") from exc
        for snapshot in profile.get("snapshots", []):
            require(snapshot, dict, "account snapshot")
            for field in ("skills", "activities"):
                require(snapshot.get(field, {}), dict, field)
                for record in snapshot.get(field, {}).values():
                    require(record, dict, field)
                    for number in (("rank", "level", "xp") if field == "skills" else ("rank", "score")):
                        if number not in record or type(record[number]) is not int:
                            raise ValueError(f"Invalid {field} {number} in save.")
        goals = list(profile.get("goal_history", []))
        if profile.get("active_goal"):
            goals.append(profile["active_goal"])
        for goal in goals:
            require(goal, dict, "goal")
            require(goal.get("metadata", {}), dict, "goal metadata")
            require(goal.get("reasons", []), list, "goal reasons")
            for field in ("start_value", "target_value", "current_value", "progress_percent"):
                if goal.get(field) is not None and type(goal[field]) not in (int, float):
                    raise ValueError(f"Invalid goal {field} in save.")
    if raw.get("last_account") is not None and not isinstance(raw["last_account"], dict):
        raise ValueError("Invalid last account in save.")
    return raw


def import_save(source: Path, destination: Path) -> bool:
    if destination.exists():
        return False
    read_save(source)
    data = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # An exclusive backup preserves the original bytes before importing.
    backup = destination.parent / "imported-original.json"
    if not backup.exists():
        with backup.open("xb") as stream:
            stream.write(data)
    temp = destination.with_suffix(".importing")
    temp.write_bytes(data)
    # Startup's application lock serializes imports and normal saves.
    temp.replace(destination)
    return True
