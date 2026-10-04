from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import ASSET_CATALOG_FILE, ASSETS_DIR, CACHE_DIR, VERSION


WIKI_API = "https://oldschool.runescape.wiki/api.php"
BUNDLED_BOSS_ICON_DIR = ASSETS_DIR / "bosses"
BUNDLED_BOSS_MANIFEST = BUNDLED_BOSS_ICON_DIR / "manifest.json"

# Explicit RuneLite HiScores boss order used to create the bundled local icon
# pack from the user-supplied RuneLite screenshot. Keeping the order in code
# makes the source mapping auditable and guards against accidental remapping.
RUNELITE_BOSS_ATLAS_ORDER: tuple[str, ...] = (
    "Abyssal Sire",
    "Alchemical Hydra",
    "Amoxliatl",
    "Araxxor",
    "Artio",
    "Barrows Chests",
    "Brutus",
    "Bryophyta",
    "Callisto",
    "Calvar'ion",
    "Cerberus",
    "Chambers of Xeric",
    "Chambers of Xeric: Challenge Mode",
    "Chaos Elemental",
    "Chaos Fanatic",
    "Commander Zilyana",
    "Corporeal Beast",
    "Crazy Archaeologist",
    "Dagannoth Prime",
    "Dagannoth Rex",
    "Dagannoth Supreme",
    "Deranged Archaeologist",
    "Doom of Mokhaiotl",
    "Duke Sucellus",
    "General Graardor",
    "Giant Mole",
    "Grotesque Guardians",
    "Hespori",
    "Kalphite Queen",
    "King Black Dragon",
    "Kraken",
    "Kree'Arra",
    "K'ril Tsutsaroth",
    "Lunar Chests",
    "Mad Angel",
    "Maggot King",
    "Mimic",
    "Nex",
    "Nightmare",
    "Phosani's Nightmare",
    "Obor",
    "Phantom Muspah",
    "Sarachnis",
    "Scorpia",
    "Scurrius",
    "Shellbane Gryphon",
    "Skotizo",
    "Sol Heredit",
    "Spindel",
    "Tempoross",
    "The Gauntlet",
    "The Corrupted Gauntlet",
    "The Hueycoatl",
    "The Leviathan",
    "The Royal Titans",
    "The Whisperer",
    "Theatre of Blood",
    "Theatre of Blood: Hard Mode",
    "Thermonuclear Smoke Devil",
    "Tombs of Amascut",
    "Tombs of Amascut: Expert Mode",
    "TzKal-Zuk",
    "TzTok-Jad",
    "Vardorvis",
    "Venenatis",
    "Vet'ion",
    "Vorkath",
    "Wintertodt",
    "Yama",
    "Zalcano",
    "Zulrah",
)


@dataclass(slots=True)
class WikiAsset:
    key: str
    wiki_filename: str
    source_url: str
    local_path: Path


class WikiAssetService:
    """Resolve display assets without making boss art a runtime dependency.

    Bosses are shipped as a fully curated local pack generated from the exact
    RuneLite HiScores screenshot supplied by the user. All 24 skill icons are
    bundled from the OSRS Wiki. Other curated items may be cached on first use.
    """

    def __init__(
        self,
        cache_dir: Path = CACHE_DIR,
        catalog_path: Path = ASSET_CATALOG_FILE,
        timeout: int = 12,
        boss_icon_dir: Path = BUNDLED_BOSS_ICON_DIR,
        boss_manifest_path: Path = BUNDLED_BOSS_MANIFEST,
    ) -> None:
        self.cache_dir = cache_dir
        self.catalog_path = catalog_path
        self.timeout = timeout
        self.boss_icon_dir = boss_icon_dir
        self.boss_manifest_path = boss_manifest_path
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.catalog = self._load_catalog()
        self.boss_manifest = self._load_boss_manifest()

    def _load_catalog(self) -> dict[str, dict[str, str]]:
        try:
            raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            key: value
            for key, value in raw.items()
            if not key.startswith("_") and isinstance(value, dict)
        }

    def _load_boss_manifest(self) -> dict[str, dict[str, object]]:
        try:
            raw = json.loads(self.boss_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        bosses = raw.get("bosses", {})
        if not isinstance(bosses, dict):
            return {}
        return {
            str(name): record
            for name, record in bosses.items()
            if isinstance(record, dict) and record.get("file")
        }

    def filename_for(self, key: str) -> str | None:
        record = self.catalog.get(key) or {}
        filename = record.get("wiki_filename")
        return str(filename) if filename else None

    def _bundled_boss_path(self, boss: str) -> Path | None:
        record = self.boss_manifest.get(boss)
        if not record:
            return None
        filename = record.get("file")
        if not filename:
            return None
        path = self.boss_icon_dir / str(filename)
        return path if path.exists() else None

    def can_fetch(self, key: str) -> bool:
        if key.startswith("boss:"):
            boss = key.split(":", 1)[1].strip()
            return self._bundled_boss_path(boss) is not None
        return bool(self.filename_for(key))

    def cached_path(self, key: str) -> Path | None:
        if key.startswith("boss:"):
            boss = key.split(":", 1)[1].strip()
            return self._bundled_boss_path(boss)

        filename = self.filename_for(key)
        if filename:
            destination = self.cache_dir / self._safe_name(filename)
            bundled = ASSETS_DIR / "cache" / self._safe_name(filename)
            return destination if destination.exists() else (bundled if bundled.exists() else None)
        return None

    def fetch_key(self, key: str) -> WikiAsset:
        if key.startswith("boss:"):
            boss = key.split(":", 1)[1].strip()
            destination = self._bundled_boss_path(boss)
            if destination is None:
                raise KeyError(f"No bundled RuneLite boss icon for {boss}")
            return WikiAsset(
                key=key,
                wiki_filename=destination.name,
                source_url="bundled:user-supplied-runelite-hiscores-screenshot",
                local_path=destination,
            )

        filename = self.filename_for(key)
        if filename:
            cached = self.cached_path(key)
            if cached is not None:
                return WikiAsset(key, filename, "cached", cached)
            return self.cache_file(key, filename)
        raise KeyError(f"No curated asset for {key}")

    def resolve_file_url(self, wiki_filename: str) -> str:
        query = urlencode({
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url",
            "titles": f"File:{wiki_filename}",
        })
        payload = self._get_json(f"{WIKI_API}?{query}")
        pages = payload.get("query", {}).get("pages", {})
        for page in pages.values():
            infos = page.get("imageinfo") or []
            if infos and infos[0].get("url"):
                return infos[0]["url"]
        raise FileNotFoundError(f"Wiki file not found: {wiki_filename}")

    def cache_file(self, key: str, wiki_filename: str) -> WikiAsset:
        destination = self.cache_dir / self._safe_name(wiki_filename)
        if destination.exists():
            return WikiAsset(key, wiki_filename, "cached", destination)

        url = self.resolve_file_url(wiki_filename)
        self._download(url, destination)
        return WikiAsset(key, wiki_filename, url, destination)

    def _get_json(self, url: str) -> dict:
        request = Request(url, headers={"User-Agent": f"OSRS-Goal-Generator/{VERSION}"})
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _download(self, url: str, destination: Path) -> None:
        request = Request(url, headers={"User-Agent": f"OSRS-Goal-Generator/{VERSION}"})
        with urlopen(request, timeout=self.timeout) as response:
            destination.write_bytes(response.read())

    @staticmethod
    def _safe_name(filename: str) -> str:
        return filename.replace("/", "_")
