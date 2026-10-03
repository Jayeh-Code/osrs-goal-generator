from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import DATA_DIR
from ..models import DiaryDefinition, PathDefinition, Requirement


DIARY_SOURCE_URL = (
    "https://raw.githubusercontent.com/AKAddons/runelite-goal-planner/"
    "main/src/main/resources/com/goalplanner/data/diary-requirements.json"
)
DIARY_CACHE_FILE = DATA_DIR / "diary_requirements.json"

TIER_ORDER = {"easy": 0, "medium": 1, "hard": 2, "elite": 3}


class DiaryDataError(RuntimeError):
    pass


class DiaryDataService:
    """Load achievement-diary requirement data and adapt it for this app.

    Product scope intentionally assumes quests are already complete. We therefore
    ignore quest prerequisites while retaining measurable skill/boss requirements.
    Items, unlock alternatives, account metrics, and the diary tasks themselves are
    treated as manual because public HiScores cannot verify them reliably.
    """

    def __init__(self, cache_file: Path = DIARY_CACHE_FILE) -> None:
        self.cache_file = cache_file
        self._definitions: list[DiaryDefinition] | None = None

    def load(self, *, force_refresh: bool = False) -> list[DiaryDefinition]:
        if self._definitions is not None and not force_refresh:
            return list(self._definitions)

        raw: dict | None = None
        if self.cache_file.exists() and not force_refresh:
            try:
                raw = json.loads(self.cache_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = None

        if raw is None:
            try:
                request = Request(
                    DIARY_SOURCE_URL,
                    headers={"User-Agent": "OSRS-Goal-Generator/4.0-alpha5"},
                )
                with urlopen(request, timeout=12) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)
                self.cache_file.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                # If refresh failed but we already have a cache, use it.
                if self.cache_file.exists():
                    try:
                        raw = json.loads(self.cache_file.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        raw = None
                if raw is None:
                    raise DiaryDataError(
                        "Could not load diary requirement data. Check your internet connection "
                        "and try Refresh Requirements again."
                    ) from exc

        self._definitions = self.parse(raw)
        return list(self._definitions)

    @staticmethod
    def _skill_name(raw: str) -> str:
        return raw.replace("_", " ").title().replace("Runecraft", "Runecraft")

    @classmethod
    def parse(cls, raw: dict) -> list[DiaryDefinition]:
        definitions: list[DiaryDefinition] = []
        if not isinstance(raw, dict):
            return definitions

        for key, payload in raw.items():
            if not isinstance(key, str) or "|" not in key or not isinstance(payload, dict):
                continue
            region, tier_raw = key.split("|", 1)
            tier = tier_raw.strip().lower()
            if tier not in TIER_ORDER:
                continue

            requirements: list[Requirement] = []
            skill_levels: dict[str, int] = {}

            def add_skill(skill_raw: str, level_raw: object) -> None:
                try:
                    level = int(level_raw)
                except (TypeError, ValueError):
                    return
                name = cls._skill_name(str(skill_raw))
                skill_levels[name] = max(skill_levels.get(name, 0), level)

            for item in payload.get("skills", []):
                if isinstance(item, dict):
                    add_skill(item.get("skill", ""), item.get("level"))

            # Some diary requirements are represented as unlock prerequisites.
            # Direct skill prerequisites are safe to merge. OR-alternatives are
            # intentionally left manual because our Requirement model is AND-only.
            unlocks = payload.get("unlocks", [])
            for unlock in unlocks:
                if not isinstance(unlock, dict):
                    continue
                for item in unlock.get("prereqSkills", []):
                    if isinstance(item, dict):
                        add_skill(item.get("skill", ""), item.get("level"))

            for skill_name, level in sorted(skill_levels.items()):
                requirements.append(Requirement(
                    requirement_id=(
                        f"diary:{region.lower().replace(' ', '_').replace('&', 'and')}:"
                        f"{tier}:skill:{skill_name.lower().replace(' ', '_')}:{level}"
                    ),
                    kind="skill",
                    target=skill_name,
                    required_value=level,
                    label=f"{skill_name} {level}",
                    weight=1.0,
                ))

            for item in payload.get("bossKills", []):
                if not isinstance(item, dict):
                    continue
                boss = str(item.get("bossName", "")).strip()
                if not boss:
                    continue
                try:
                    count = int(item.get("killCount", 1))
                except (TypeError, ValueError):
                    count = 1
                requirements.append(Requirement(
                    requirement_id=(
                        f"diary:{region.lower().replace(' ', '_').replace('&', 'and')}:"
                        f"{tier}:boss:{boss.lower().replace(' ', '_')}:{count}"
                    ),
                    kind="boss_kc",
                    target=boss,
                    required_value=count,
                    label=f"{boss} {count} KC",
                    weight=1.5,
                ))

            manual_count = 0
            manual_count += len(payload.get("itemReqs", []) or [])
            manual_count += len(payload.get("accountReqs", []) or [])

            for unlock in unlocks:
                if not isinstance(unlock, dict):
                    continue
                if unlock.get("alternatives"):
                    manual_count += 1
                elif unlock.get("itemId"):
                    manual_count += 1
                elif unlock.get("prereqAccounts"):
                    manual_count += 1

            # Even when all stats are ready, public HiScores do not expose the
            # completion state of the diary tier itself. This manual requirement
            # keeps a tracked diary from auto-completing until the player confirms it.
            requirements.append(Requirement(
                requirement_id=(
                    f"diary:{region.lower().replace(' ', '_').replace('&', 'and')}:"
                    f"{tier}:manual_completion"
                ),
                kind="manual",
                target=f"{region} {tier.title()} Diary",
                required_value=None,
                label="Complete remaining diary tasks",
                weight=0.5,
                manual=True,
                note="Diary completion is not exposed by public HiScores.",
            ))

            diary_id = f"{region.lower().replace(' ', '_').replace('&', 'and')}:{tier}"
            definitions.append(DiaryDefinition(
                diary_id=diary_id,
                name=region,
                tier=tier,
                requirements=tuple(requirements),
                source_url=DIARY_SOURCE_URL,
                description=(
                    "Quest prerequisites are assumed complete. Readiness reflects measurable "
                    "skill/boss requirements; remaining tasks are confirmed manually."
                ),
                manual_requirement_count=manual_count,
            ))

        definitions.sort(key=lambda d: (d.name.lower(), TIER_ORDER.get(d.tier, 99)))
        return definitions

    @staticmethod
    def as_path(diary: DiaryDefinition) -> PathDefinition:
        return PathDefinition(
            path_id=f"diary:{diary.diary_id}",
            name=f"{diary.name} {diary.tier.title()} Diary",
            category="diary",
            requirements=diary.requirements,
            description=diary.description,
            source_url=diary.source_url,
            is_custom=False,
        )
