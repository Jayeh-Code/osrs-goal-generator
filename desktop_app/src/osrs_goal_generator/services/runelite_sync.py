from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import PlayerProfile, Skill, Activity
from ..boss_rates import BOSS_RATES


DEFAULT_RUNELITE_SYNC_PATH = (
    Path.home() / ".runelite" / "plugin-data" / "osrs-goal-generator-companion" / "sync.json"
)


@dataclass(slots=True, frozen=True)
class RuneLiteCollectionItem:
    item_id: int
    name: str
    obtained: bool


@dataclass(slots=True, frozen=True)
class RuneLiteCollectionPage:
    name: str
    items: tuple[RuneLiteCollectionItem, ...] = ()
    updated_at: str = ""

    @property
    def obtained_count(self) -> int:
        return sum(1 for item in self.items if item.obtained)

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def missing_items(self) -> tuple[RuneLiteCollectionItem, ...]:
        return tuple(item for item in self.items if not item.obtained)


@dataclass(slots=True, frozen=True)
class RuneLiteSyncSnapshot:
    schema_version: int
    plugin_version: str
    updated_at: str
    connected: bool
    game_state: str
    player_name: str
    account_type: str
    combat_level: int | None
    total_level: int | None
    total_xp: int | None
    skills: dict[str, dict[str, int]] = field(default_factory=dict)
    boss_counts: dict[str, int] = field(default_factory=dict)
    session: dict[str, Any] = field(default_factory=dict)
    collection_pages: dict[str, RuneLiteCollectionPage] = field(default_factory=dict)
    recent_collection_unlocks: tuple[str, ...] = ()

    def age_seconds(self, now: datetime | None = None) -> float | None:
        try:
            timestamp = datetime.fromisoformat(self.updated_at.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return max(0.0, (current - timestamp).total_seconds())

    def is_fresh(self, max_age_seconds: int = 20) -> bool:
        age = self.age_seconds()
        return bool(self.connected and age is not None and age <= max_age_seconds)

    def matches(self, profile: PlayerProfile | None) -> bool:
        if profile is None or not self.player_name:
            return False
        return profile.rsn.strip().casefold() == self.player_name.strip().casefold()

    @property
    def collection_page_count(self) -> int:
        return len(self.collection_pages)

    @property
    def collection_item_count(self) -> int:
        return sum(page.total_count for page in self.collection_pages.values())

    @property
    def collection_obtained_count(self) -> int:
        return sum(page.obtained_count for page in self.collection_pages.values())


class RuneLiteSyncService:
    """Read the local RuneLite companion file and merge live account data.

    The bridge is deliberately local-only.  The RuneLite plugin writes an
    atomic JSON snapshot beneath RuneLite's own data directory; the desktop
    app reads it.  No credentials, network server, or process-memory access is
    involved.
    """

    def __init__(self, path: Path = DEFAULT_RUNELITE_SYNC_PATH) -> None:
        self.path = Path(path)

    def load(self) -> RuneLiteSyncSnapshot | None:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        if type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
            return None

        player = raw.get("player") if isinstance(raw.get("player"), dict) else {}
        skills_raw = raw.get("skills") if isinstance(raw.get("skills"), dict) else {}
        skills: dict[str, dict[str, int]] = {}
        for name, value in skills_raw.items():
            if not isinstance(name, str) or not isinstance(value, dict):
                continue
            try:
                level = int(value.get("level", 0))
                xp = int(value.get("xp", 0))
            except (TypeError, ValueError):
                continue
            if level < 1 or xp < 0:
                continue
            skills[name] = {"level": level, "xp": xp}

        pages_raw = raw.get("collection_log")
        pages_block = pages_raw if isinstance(pages_raw, dict) else {}
        pages_value = pages_block.get("pages") if isinstance(pages_block.get("pages"), dict) else {}
        collection_pages: dict[str, RuneLiteCollectionPage] = {}
        for page_name, page_raw in pages_value.items():
            if not isinstance(page_name, str) or not isinstance(page_raw, dict):
                continue
            items: list[RuneLiteCollectionItem] = []
            page_items = page_raw.get("items", [])
            if not isinstance(page_items, list):
                page_items = []
            for item in page_items:
                if not isinstance(item, dict):
                    continue
                try:
                    item_id = int(item.get("item_id", -1))
                except (TypeError, ValueError):
                    continue
                if item_id < 0:
                    continue
                items.append(
                    RuneLiteCollectionItem(
                        item_id=item_id,
                        name=str(item.get("name", f"Item {item_id}")),
                        obtained=item.get("obtained") is True,
                    )
                )
            collection_pages[page_name] = RuneLiteCollectionPage(
                name=page_name,
                items=tuple(items),
                updated_at=str(page_raw.get("updated_at", raw.get("updated_at", ""))),
            )

        unlocks = pages_block.get("recent_unlocks", [])
        if not isinstance(unlocks, list):
            unlocks = []

        def optional_int(value: Any) -> int | None:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        return RuneLiteSyncSnapshot(
            schema_version=1,
            plugin_version=str(raw.get("plugin_version", "unknown")),
            updated_at=str(raw.get("updated_at", "")),
            connected=bool(raw.get("connected", False)),
            game_state=str(raw.get("game_state", "UNKNOWN")),
            player_name=str(player.get("name", "")),
            account_type=str(player.get("account_type", "unknown")),
            combat_level=optional_int(player.get("combat_level")),
            total_level=optional_int(player.get("total_level")),
            total_xp=optional_int(player.get("total_xp")),
            skills=skills,
            boss_counts={name: count for name, count in
                         (raw.get('boss_counts', {}) if isinstance(raw.get('boss_counts'), dict) else {}).items()
                         if name in BOSS_RATES and type(count) is int and 0 <= count <= 2147483647},
            session=deepcopy(raw.get("session", {})) if isinstance(raw.get("session"), dict) else {},
            collection_pages=collection_pages,
            recent_collection_unlocks=tuple(str(item) for item in unlocks[:20]),
        )

    @staticmethod
    def fingerprint(snapshot: RuneLiteSyncSnapshot | None) -> tuple[Any, ...] | None:
        if snapshot is None:
            return None
        skill_values = tuple(
            sorted((name, values.get("level", 0), values.get("xp", 0)) for name, values in snapshot.skills.items())
        )
        collection_values = tuple(
            sorted(
                (
                    name,
                    tuple((item.item_id, item.obtained) for item in page.items),
                )
                for name, page in snapshot.collection_pages.items()
            )
        )
        return (
            snapshot.connected,
            snapshot.player_name.casefold(),
            skill_values,
            tuple(sorted(snapshot.boss_counts.items())),
            collection_values,
            snapshot.recent_collection_unlocks,
        )

    @staticmethod
    def merge_profile(profile: PlayerProfile, snapshot: RuneLiteSyncSnapshot) -> PlayerProfile:
        """Return an in-memory profile with RuneLite skill/XP data overlaid.

        Explicit live boss totals overlay lagging HiScores without reducing counts.  Ranks are also kept
        from HiScores because RuneLite does not know them locally.
        """

        merged = PlayerProfile.from_dict(profile.to_dict())
        for name, live in snapshot.skills.items():
            existing = merged.skill(name)
            if existing is None:
                merged.skills[name] = Skill(
                    name=name,
                    rank=-1,
                    level=int(live["level"]),
                    xp=int(live["xp"]),
                )
                continue
            existing.level = int(live["level"])
            existing.xp = int(live["xp"])

        if snapshot.is_fresh() and snapshot.matches(profile) and snapshot.game_state == 'LOGGED_IN':
            for name, count in snapshot.boss_counts.items():
                existing = merged.activity(name)
                if existing is None:
                    merged.activities[name] = Activity(name, -1, count)
                else:
                    existing.score = max(existing.score, count)
        overall = merged.overall
        if overall is not None:
            if snapshot.total_level is not None:
                overall.level = snapshot.total_level
            if snapshot.total_xp is not None:
                overall.xp = snapshot.total_xp
        return merged
