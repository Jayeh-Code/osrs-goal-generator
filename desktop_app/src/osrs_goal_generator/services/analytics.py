from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from ..models import Goal, PlayerProfile


@dataclass(slots=True)
class SkillGain:
    name: str
    xp_delta: int
    level_delta: int
    start_level: int
    end_level: int


@dataclass(slots=True)
class ActivityGain:
    name: str
    delta: int
    start_value: int
    end_value: int


@dataclass(slots=True)
class AnalyticsSummary:
    snapshot_count: int = 0
    tracked_from: str | None = None
    tracked_to: str | None = None
    total_xp_gained: int = 0
    total_levels_gained: int = 0
    skill_gains: list[SkillGain] = field(default_factory=list)
    activity_gains: list[ActivityGain] = field(default_factory=list)
    accepted_tasks: int = 0
    completed_tasks: int = 0
    cancelled_tasks: int = 0
    blocked_tasks: int = 0
    active_tasks: int = 0
    completion_rate: float = 0.0
    category_counts: dict[str, int] = field(default_factory=dict)
    completed_category_counts: dict[str, int] = field(default_factory=dict)
    favorite_category: str | None = None
    strongest_category: str | None = None

    @property
    def tracking_days(self) -> int:
        if not self.tracked_from or not self.tracked_to:
            return 0
        try:
            start = datetime.fromisoformat(self.tracked_from)
            end = datetime.fromisoformat(self.tracked_to)
        except ValueError:
            return 0
        return max(0, (end - start).days)


class AnalyticsService:
    """Summarize local account snapshots and accepted-task history.

    The service deliberately uses only data the app has actually observed. It
    does not extrapolate playtime, XP/hour, or untracked account progress.
    """

    def summarize(
        self,
        snapshots: list[PlayerProfile],
        history: list[Goal],
        active_goal: Goal | None = None,
    ) -> AnalyticsSummary:
        summary = AnalyticsSummary(snapshot_count=len(snapshots))

        if snapshots:
            first = snapshots[0]
            last = snapshots[-1]
            summary.tracked_from = first.fetched_at
            summary.tracked_to = last.fetched_at

            overall_first = first.overall
            overall_last = last.overall
            if overall_first and overall_last:
                summary.total_xp_gained = max(0, overall_last.xp - overall_first.xp)
                summary.total_levels_gained = max(0, overall_last.level - overall_first.level)

            for name, end_skill in last.skills.items():
                if name == "Overall":
                    continue
                start_skill = first.skills.get(name)
                if not start_skill:
                    continue
                xp_delta = max(0, end_skill.xp - start_skill.xp)
                level_delta = max(0, end_skill.level - start_skill.level)
                if xp_delta or level_delta:
                    summary.skill_gains.append(SkillGain(
                        name=name,
                        xp_delta=xp_delta,
                        level_delta=level_delta,
                        start_level=start_skill.level,
                        end_level=end_skill.level,
                    ))

            for name, end_activity in last.activities.items():
                start_activity = first.activities.get(name)
                start_score = 0 if start_activity is None or start_activity.score < 0 else start_activity.score
                end_score = 0 if end_activity.score < 0 else end_activity.score
                delta = max(0, end_score - start_score)
                if delta:
                    summary.activity_gains.append(ActivityGain(
                        name=name,
                        delta=delta,
                        start_value=start_score,
                        end_value=end_score,
                    ))

            summary.skill_gains.sort(key=lambda item: (item.xp_delta, item.level_delta), reverse=True)
            summary.activity_gains.sort(key=lambda item: item.delta, reverse=True)

        category_counts: Counter[str] = Counter()
        completed_category_counts: Counter[str] = Counter()
        for goal in history:
            category = goal.category or "unknown"
            category_counts[category] += 1
            if goal.status == "completed":
                completed_category_counts[category] += 1

            if goal.status == "completed":
                summary.completed_tasks += 1
            elif goal.status == "cancelled":
                summary.cancelled_tasks += 1
            elif goal.status == "blocked":
                summary.blocked_tasks += 1
            elif goal.status == "accepted":
                summary.active_tasks += 1

        # History contains every accepted task once. Older save formats may not
        # include a currently active goal in history, so guard against that.
        summary.accepted_tasks = len(history)
        if active_goal and not any(goal.goal_id == active_goal.goal_id for goal in history):
            summary.accepted_tasks += 1
            summary.active_tasks += 1
            category_counts[active_goal.category or "unknown"] += 1

        resolved = summary.completed_tasks + summary.cancelled_tasks + summary.blocked_tasks
        summary.completion_rate = (
            summary.completed_tasks / resolved * 100.0
            if resolved else 0.0
        )

        summary.category_counts = dict(category_counts)
        summary.completed_category_counts = dict(completed_category_counts)
        if category_counts:
            summary.favorite_category = category_counts.most_common(1)[0][0]
        if completed_category_counts:
            summary.strongest_category = completed_category_counts.most_common(1)[0][0]
        return summary
