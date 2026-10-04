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
