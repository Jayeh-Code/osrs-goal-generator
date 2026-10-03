from __future__ import annotations

import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import ACCOUNT_ENDPOINTS, VERSION
from ..models import Activity, PlayerProfile, Skill


class HiscoresError(RuntimeError):
    pass


class HiscoresClient:
    """Small adapter around Jagex's name-based JSON HiScores response."""

    def __init__(self, timeout: int = 12) -> None:
        self.timeout = timeout

    def fetch(self, rsn: str, account_type: str = "normal") -> PlayerProfile:
        rsn = " ".join(rsn.strip().split())
        if not rsn:
            raise HiscoresError("RuneScape name cannot be blank.")
        if account_type not in ACCOUNT_ENDPOINTS:
            raise HiscoresError(f"Unsupported account type: {account_type}")

        url = f"{ACCOUNT_ENDPOINTS[account_type]}?{urlencode({'player': rsn})}"
        request = Request(
            url,
            headers={"User-Agent": f"OSRS-Goal-Generator/{VERSION}"},
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code == 404:
                raise HiscoresError(f'No HiScores profile found for "{rsn}".') from exc
            raise HiscoresError(f"Jagex returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            raise HiscoresError("Could not reach the OSRS HiScores.") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HiscoresError("Jagex returned invalid HiScores JSON.") from exc

        skills: dict[str, Skill] = {}
        for item in payload.get("skills", []):
            name = item.get("name")
            if not name:
                continue
            skills[name] = Skill(
                name=name,
                rank=int(item.get("rank", -1)),
                level=int(item.get("level", -1)),
                xp=int(item.get("xp", -1)),
            )

        activities: dict[str, Activity] = {}
        for item in payload.get("activities", []):
            name = item.get("name")
            if not name:
                continue
            activities[name] = Activity(
                name=name,
                rank=int(item.get("rank", -1)),
                score=int(item.get("score", -1)),
            )

        if "Overall" not in skills:
            raise HiscoresError("HiScores response did not include Overall skill data.")

        return PlayerProfile(
            rsn=rsn,
            account_type=account_type,
            fetched_at=datetime.now().isoformat(timespec="seconds"),
            skills=skills,
            activities=activities,
        )
