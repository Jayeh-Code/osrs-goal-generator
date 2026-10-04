"""User-facing bridge state; connection freshness does not imply fresh log pages."""
from dataclasses import dataclass
from ..models import Goal, PlayerProfile
from .runelite_sync import RuneLiteSyncSnapshot


@dataclass(frozen=True)
class BridgeStatus:
    title: str
    detail: str
    live: bool = False


def bridge_status(snapshot: RuneLiteSyncSnapshot | None, profile: PlayerProfile | None,
                  goal: Goal | None = None, *, file_exists: bool = False) -> BridgeStatus:
    if snapshot is None:
        if file_exists:
            return BridgeStatus("BRIDGE UNAVAILABLE", "The local RuneLite data could not be read. Check that the companion is enabled; the desktop will retry automatically. HiScores remains available.")
        return BridgeStatus("RUNELITE NOT DETECTED", "Enable the companion and log in to RuneLite for live progress. HiScores remains available.")
    if not snapshot.connected or snapshot.game_state != "LOGGED_IN":
        return BridgeStatus("RUNELITE DISCONNECTED", "Log in with the companion enabled to resume live progress. Previously captured collection pages remain cached; HiScores remains available.")
    if not snapshot.is_fresh():
        return BridgeStatus("RUNELITE NOT UPDATING", "No recent heartbeat from RuneLite. Check the client and companion. Previously captured pages are cached; HiScores remains available.")
    if profile is None:
        return BridgeStatus("RUNELITE CONNECTED", f"RuneLite is connected as {snapshot.player_name}. Load that account in the desktop to track live progress.")
    if not snapshot.matches(profile):
        return BridgeStatus("ACCOUNT MISMATCH", f"RuneLite is logged in as {snapshot.player_name}; the desktop has {profile.rsn}. Use the same account in both apps. HiScores remains available.")
    if goal and goal.subtype == "collection_slot":
        page = snapshot.collection_pages.get(goal.target_name)
        tracked = set(goal.metadata.get("collection_item_ids", []))
        complete_page = bool(page and tracked and tracked.issubset({item.item_id for item in page.items}))
        event = str(snapshot.session.get("last_event", ""))
        unlock_name = event.removeprefix("collection_unlock:").strip().casefold() if event.startswith("collection_unlock:") else ""
        pending_unlock = bool(page and unlock_name and any(
            item.item_id in tracked and not item.obtained and item.name.strip().casefold() == unlock_name
            for item in page.items))
        if not complete_page or pending_unlock:
            return BridgeStatus("WAITING FOR PAGE REFRESH", f"RuneLite is live. Open Collection Log > {goal.target_name} in game to verify your tracked items. An unlock message alone does not complete the goal.", True)
        return BridgeStatus("RUNELITE LIVE", f"Tracking {goal.target_name}. Reopen this Collection Log page after an unlock so the desktop can verify completion. Live XP does not refresh collection pages.", True)
    return BridgeStatus("RUNELITE LIVE", "Skill XP is updating from RuneLite. Collection pages reflect the last time you opened them in game.", True)
