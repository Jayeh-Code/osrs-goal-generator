from pathlib import Path

APP_NAME = "OSRS Goal Generator"
VERSION = "4.0.0-alpha.9.0"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent.parent
DATA_DIR = PROJECT_DIR / "user_data"
ASSETS_DIR = PROJECT_DIR / "assets"
CACHE_DIR = ASSETS_DIR / "cache"
ASSET_CATALOG_FILE = ASSETS_DIR / "catalog.json"
STATE_FILE = DATA_DIR / "state.json"
RUNELITE_SYNC_FILE = Path.home() / ".runelite" / "plugin-data" / "osrs-goal-generator-companion" / "sync.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

ACCOUNT_ENDPOINTS = {
    "normal": "https://services.runescape.com/m=hiscore_oldschool/index_lite.json",
    "ironman": "https://services.runescape.com/m=hiscore_oldschool_ironman/index_lite.json",
    "hardcore": "https://services.runescape.com/m=hiscore_oldschool_hardcore_ironman/index_lite.json",
    "ultimate": "https://services.runescape.com/m=hiscore_oldschool_ultimate/index_lite.json",
}

ACCOUNT_LABELS = {
    "normal": "Main / Normal",
    "ironman": "Ironman",
    "hardcore": "Hardcore Ironman",
    "ultimate": "Ultimate Ironman",
}

DEFAULT_SESSION_MINUTES = 60
DEFAULT_DIFFICULTY = "moderate"
