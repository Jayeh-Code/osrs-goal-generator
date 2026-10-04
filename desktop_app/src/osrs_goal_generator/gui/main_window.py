from __future__ import annotations

import uuid

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..account_math import combat_level, level_progress, lowest_skills
from ..boss_rates import all_boss_names, boss_rate
from ..config import ACCOUNT_LABELS, APP_NAME, VERSION
from ..engine.goal_engine import BOSS_MARKERS, GoalEngine
from ..engine.scoring import ScoringContext
from ..models import DiaryDefinition, Goal, GoalFilters, PathDefinition, PlayerProfile
from ..services.analytics import AnalyticsService
from ..services.bridge_status import bridge_status
from ..services.collection_categories import CATEGORIES, collection_page_category
from ..services.diaries import DiaryDataError, DiaryDataService
from ..services.hiscores import HiscoresClient, HiscoresError
from ..services.progress import GoalProgressService, compare_profiles
from ..services.progression import ProgressionService
from ..services.storage import StateStore
from ..services.runelite_sync import RuneLiteSyncService, RuneLiteSyncSnapshot
from ..services.wiki_assets import WikiAssetService
from .path_dialog import CustomPathDialog
from .collection_dialog import CollectionTargetDialog
from .theme import APP_STYLESHEET


class FetchWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, rsn: str, account_type: str) -> None:
        super().__init__()
        self.rsn = rsn
        self.account_type = account_type

    def run(self) -> None:
        try:
            self.finished.emit(HiscoresClient().fetch(self.rsn, self.account_type))
        except HiscoresError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - GUI safety net
            self.failed.emit(f"Unexpected lookup error: {exc}")


class AssetBatchWorker(QObject):
    finished = Signal(object)

    def __init__(self, keys: list[str]) -> None:
        super().__init__()
        self.keys = keys

    def run(self) -> None:
        service = WikiAssetService()
        result: dict[str, str] = {}
        for key in self.keys:
            try:
                asset = service.fetch_key(key)
                result[key] = str(asset.local_path)
            except Exception:
                # Asset failures should never break the core app.
                continue
        self.finished.emit(result)


@dataclass
class AppSession:
    profile: PlayerProfile | None = None
    previous_profile: PlayerProfile | None = None
    current_goal: Goal | None = None


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} - {VERSION}")
        self.resize(1500, 920)
        self.setMinimumSize(1180, 760)
        self.setStyleSheet(APP_STYLESHEET)

        self.store = StateStore()
        self.state = self.store.load()
        self.session = AppSession()
        self.goal_engine = GoalEngine()
        self.progress_service = GoalProgressService()
        self.progression_service = ProgressionService()
        self.analytics_service = AnalyticsService()
        self.diary_service = DiaryDataService()
        self.diary_definitions: list[DiaryDefinition] = []
        self.diary_error: str | None = None
        self.asset_service = WikiAssetService()
        self.runelite_sync_service = RuneLiteSyncService()
        self.runelite_snapshot: RuneLiteSyncSnapshot | None = None
        self.runelite_fingerprint: tuple | None = None
        self.fetch_thread: QThread | None = None
        self.asset_thread: QThread | None = None
        self.pending_asset_keys: set[str] = set()
        self.asset_attempted: set[str] = set()
        self.cached_assets: dict[str, Path] = {}

        self.pages = QStackedWidget()
        self.home_page = self._build_home_page()
        self.bosses_page = self._build_bosses_page()
        self.paths_page = self._build_paths_page()
        self.diaries_page = self._build_diaries_page()
        self.collection_page = self._build_collection_page()
        self.stats_page = self._build_stats_page()
        self.history_page = self._build_history_page()
        self.settings_page = self._build_settings_page()

        for page in [
            self.home_page,
            self.bosses_page,
            self.paths_page,
            self.diaries_page,
            self.collection_page,
            self.stats_page,
            self.history_page,
            self.settings_page,
        ]:
            self.pages.addWidget(page)

        sidebar = self._build_sidebar()
        topbar = self._build_topbar()

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(topbar)
        self.bridge_status_note = QLabel()
        self.bridge_status_note.setObjectName("Muted")
        self.bridge_status_note.setWordWrap(True)
        self.bridge_status_note.setContentsMargins(26, 8, 26, 8)
        content_layout.addWidget(self.bridge_status_note)
        content_layout.addWidget(self.pages, 1)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

        self._restore_last_account()
        self._render_topbar()
        self._render_goal_panel()
        self._render_progress()

        # Local RuneLite companion bridge.  Polling a small atomic JSON file is
        # intentionally simple and keeps Alpha 8 serverless/offline-capable.
        self.runelite_timer = QTimer(self)
        self.runelite_timer.setInterval(2000)
        self.runelite_timer.timeout.connect(self._poll_runelite_sync)
        self.runelite_timer.start()
        self._poll_runelite_sync()

    # ------------------------------------------------------------------
    # Shell / navigation
    # ------------------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Sidebar")
        frame.setFixedWidth(205)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 20, 16, 18)
        layout.setSpacing(4)

        brand = QLabel("OSRS GOAL\nGENERATOR")
        brand.setObjectName("Brand")
        layout.addWidget(brand)
        tagline = QLabel("SAME GAME. A CLEARER PATH.")
        tagline.setObjectName("BrandSub")
        layout.addWidget(tagline)
        layout.addSpacing(22)

        entries = [
            ("Home", "Home"),
            ("Bosses", "Bosses"),
            ("Paths", "Paths"),
            ("Diaries", "Diaries"),
            ("Collection Log", "Collection Log"),
            ("Stats", "Stats"),
            ("History", "History"),
            ("Settings", "Settings"),
        ]
        self.nav_buttons: list[QPushButton] = []
        for index, (display, label) in enumerate(entries):
            button = QPushButton(display)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setProperty("pageName", label)
            button.clicked.connect(lambda checked=False, i=index: self._switch_page(i))
            layout.addWidget(button)
            self.nav_buttons.append(button)
        self.nav_buttons[0].setChecked(True)

        layout.addStretch(1)
        source = QLabel("Public HiScores + local progression")
        source.setObjectName("Muted")
        source.setWordWrap(True)
        layout.addWidget(source)
        version = QLabel(VERSION)
        version.setObjectName("BrandSub")
        layout.addWidget(version)
        return frame

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(66)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 10, 24, 10)
        layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        self.top_page_label = QLabel("HOME")
        self.top_page_label.setObjectName("PageEyebrow")
        self.top_subtitle = QLabel("Your account command center")
        self.top_subtitle.setObjectName("Muted")
        title_box.addWidget(self.top_page_label)
        title_box.addWidget(self.top_subtitle)
        layout.addLayout(title_box)
        layout.addStretch(1)

        self.top_status_label = QLabel("OFFLINE")
        self.top_status_label.setObjectName("GoldPill")
        layout.addWidget(self.top_status_label)
        self.top_account_label = QLabel("No account loaded")
        self.top_account_label.setObjectName("SectionTitle")
        layout.addWidget(self.top_account_label)

        refresh = QPushButton("Refresh")
        refresh.setObjectName("Secondary")
        refresh.clicked.connect(self._load_account)
        self.top_refresh_button = refresh
        layout.addWidget(refresh)
        return bar

    def _render_topbar(self) -> None:
        page_names = [
            ("HOME", "Your account command center"),
            ("BOSSES", "KC, session targets, and boss-specific goals"),
            ("PATHS", "Long-term progression and current blockers"),
            ("DIARIES", "Achievement Diary readiness and blockers"),
            ("COLLECTION LOG", "Collection progression"),
            ("STATS", "Observed account and task analytics"),
            ("HISTORY", "Your generated-task journal"),
            ("SETTINGS", "Preferences, blocks, and local data"),
        ]
        index = self.pages.currentIndex() if hasattr(self, "pages") else 0
        name, subtitle = page_names[index] if 0 <= index < len(page_names) else page_names[0]
        self.top_page_label.setText(name)
        self.top_subtitle.setText(subtitle)

        profile = self.session.profile
        active = self.store.active_goal(self.state, profile) if profile else None
        status = bridge_status(self.runelite_snapshot, profile, active,
                               file_exists=self.runelite_sync_service.path.exists())
        if profile is None:
            self.top_account_label.setText("No account loaded")
            self.top_status_label.setText("OFFLINE")
            self.top_status_label.setObjectName("GoldPill")
            self.top_refresh_button.setEnabled(bool(getattr(self, "rsn_input", None) and self.rsn_input.text().strip()))
        else:
            self.top_account_label.setText(profile.rsn)
            live = self._runelite_is_live_for_profile(profile)
            self.top_status_label.setText("RUNELITE LIVE" if live else "HISCORES")
            self.top_status_label.setObjectName("Pill" if live else "GoldPill")
            self.top_refresh_button.setEnabled(True)
        self.top_status_label.setText(status.title)
        self.top_status_label.setObjectName("Pill" if status.live else "GoldPill")
        self.top_status_label.setToolTip(status.detail)
        if hasattr(self, "bridge_status_note"):
            self.bridge_status_note.setText(status.detail)
        self.top_status_label.style().unpolish(self.top_status_label)
        self.top_status_label.style().polish(self.top_status_label)

    def _switch_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        self._render_topbar()
        if index == 0:
            self._render_home()
            self._render_progress()
        elif index == 1:
            self._render_bosses()
        elif index == 2:
            self._render_paths()
        elif index == 3:
            self._render_diaries()
        elif index == 4:
            self._render_collection()
        elif index == 5:
            self._render_stats()
        elif index == 6:
            self._render_history()
        elif index == 7:
            self._render_settings()

    # ------------------------------------------------------------------
    # Home - command center
    # ------------------------------------------------------------------

    def _build_home_page(self) -> QWidget:
        """Build the Home command center using the approved mockup hierarchy.

        Alpha 6.1 intentionally mirrors the design reference much more closely:
        a large generation hero on the left, account/lowest-skill intelligence on
        the right, and three compact information cards along the bottom.
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(14, 14, 14, 18)
        outer.setSpacing(12)

        # Compact account lookup strip. The mockup keeps lookup/status in the
        # header area rather than consuming a full dashboard card.
        lookup = QFrame()
        lookup.setObjectName("TopStatStrip")
        lookup_row = QHBoxLayout(lookup)
        lookup_row.setContentsMargins(14, 8, 14, 8)
        lookup_row.setSpacing(9)
        account_tag = QLabel("ACCOUNT")
        account_tag.setObjectName("PageEyebrow")
        self.rsn_input = QLineEdit()
        self.rsn_input.setPlaceholderText("RuneScape name")
        self.rsn_input.setMaximumWidth(240)
        self.account_type = QComboBox()
        self.account_type.setMaximumWidth(180)
        for key, label in ACCOUNT_LABELS.items():
            self.account_type.addItem(label, key)
        self.load_button = QPushButton("Load / Refresh")
        self.load_button.setObjectName("Secondary")
        self.load_button.clicked.connect(self._load_account)
        lookup_row.addWidget(account_tag)
        lookup_row.addWidget(self.rsn_input)
        lookup_row.addWidget(self.account_type)
        lookup_row.addWidget(self.load_button)
        lookup_row.addStretch(1)
        hint = QLabel("Public HiScores | local progression history")
        hint.setObjectName("Muted")
        lookup_row.addWidget(hint)
        outer.addWidget(lookup)

        main_row = QHBoxLayout()
        main_row.setSpacing(12)

        # ------------------------------------------------------------------
        # Hero / Goal command center - intentionally dominant like mockup.
        # ------------------------------------------------------------------
        hero = QFrame()
        hero.setObjectName("DashboardHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        hero_layout.setSpacing(12)

        hero_head = QHBoxLayout()
        hero_text = QVBoxLayout()
        hero_text.setSpacing(1)
        hero_title = QLabel("What should you do today?")
        hero_title.setObjectName("HeroHeading")
        hero_sub = QLabel("Let the goal generator find your next useful adventure.")
        hero_sub.setObjectName("HeroSub")
        hero_text.addWidget(hero_title)
        hero_text.addWidget(hero_sub)
        hero_head.addLayout(hero_text)
        hero_head.addStretch(1)
        self.goal_mode_label = QLabel("READY")
        self.goal_mode_label.setObjectName("GoldPill")
        hero_head.addWidget(self.goal_mode_label, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(hero_head)

        self.generate_button = QPushButton("GENERATE GOAL")
        self.generate_button.setObjectName("HeroGenerate")
        self.generate_button.setMinimumHeight(72)
        self.generate_button.clicked.connect(self._generate_goal)
        hero_layout.addWidget(self.generate_button)

        filter_panel = QFrame()
        filter_panel.setObjectName("HeroControls")
        filter_grid = QGridLayout(filter_panel)
        filter_grid.setContentsMargins(14, 10, 14, 10)
        filter_grid.setHorizontalSpacing(14)
        filter_grid.setVerticalSpacing(5)

        focus_label = QLabel("Activity Focus")
        focus_label.setObjectName("StatLabel")
        session_label = QLabel("Session Length")
        session_label.setObjectName("StatLabel")
        intensity_label = QLabel("Intensity")
        intensity_label.setObjectName("StatLabel")

        self.category_combo = QComboBox()
        self.category_combo.addItems([
            "Surprise Me", "Skilling", "Bossing", "Clues", "Collection", "Progression", "Money",
        ])
        self.difficulty_combo = QComboBox()
        self.difficulty_combo.addItems(["Chill", "Moderate", "Grind"])
        self.session_combo = QComboBox()
        self.session_combo.addItem("15 Minutes", 15)
        self.session_combo.addItem("30 Minutes", 30)
        self.session_combo.addItem("1 Hour", 60)
        self.session_combo.addItem("2+ Hours", 120)
        self.session_combo.setCurrentIndex(2)

        filter_grid.addWidget(focus_label, 0, 0)
        filter_grid.addWidget(session_label, 0, 1)
        filter_grid.addWidget(intensity_label, 0, 2)
        filter_grid.addWidget(self.category_combo, 1, 0)
        filter_grid.addWidget(self.session_combo, 1, 1)
        filter_grid.addWidget(self.difficulty_combo, 1, 2)
        hero_layout.addWidget(filter_panel)

        # Generated/active goal card lives inside the hero instead of in a
        # separate Generate tab.
        goal_panel = QFrame()
        goal_panel.setObjectName("GoalPanel")
        goal_panel_layout = QVBoxLayout(goal_panel)
        goal_panel_layout.setContentsMargins(14, 12, 14, 12)
        goal_panel_layout.setSpacing(9)

        goal_row = QHBoxLayout()
        goal_row.setSpacing(14)
        self.goal_icon = QLabel("GOAL")
        self.goal_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.goal_icon.setFixedSize(78, 78)
        self.goal_icon.setObjectName("SpriteWell")
        goal_row.addWidget(self.goal_icon, 0, Qt.AlignmentFlag.AlignTop)
        goal_copy = QVBoxLayout()
        goal_copy.setSpacing(3)
        self.goal_title = QLabel("No goal generated yet")
        self.goal_title.setObjectName("GoalTitle")
        self.goal_objective = QLabel("Load an account, choose your focus, then generate a goal.")
        self.goal_objective.setWordWrap(True)
        self.home_active_progress = QProgressBar()
        self.home_active_progress.setRange(0, 100)
        self.home_active_progress.setValue(0)
        self.home_active_progress.setVisible(False)
        self.home_active_status = QLabel("")
        self.home_active_status.setObjectName("Muted")
        goal_copy.addWidget(self.goal_title)
        goal_copy.addWidget(self.goal_objective)
        goal_copy.addWidget(self.home_active_progress)
        goal_copy.addWidget(self.home_active_status)
        goal_row.addLayout(goal_copy, 1)
        goal_panel_layout.addLayout(goal_row)

        why_title = QLabel("WHY THIS GOAL?")
        why_title.setObjectName("CardTitle")
        self.goal_reasons = QLabel("-")
        self.goal_reasons.setWordWrap(True)
        self.goal_bonus = QLabel("")
        self.goal_bonus.setWordWrap(True)
        self.goal_bonus.setObjectName("Success")
        self.goal_score_hint = QLabel("")
        self.goal_score_hint.setObjectName("Muted")
        goal_panel_layout.addWidget(why_title)
        goal_panel_layout.addWidget(self.goal_reasons)
        goal_panel_layout.addWidget(self.goal_bonus)
        goal_panel_layout.addWidget(self.goal_score_hint)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.accept_goal_button = QPushButton("Accept Task")
        self.accept_goal_button.setObjectName("Primary")
        self.accept_goal_button.clicked.connect(self._accept_goal)
        self.reroll_goal_button = QPushButton("Reroll")
        self.reroll_goal_button.setObjectName("Secondary")
        self.reroll_goal_button.clicked.connect(self._reroll_goal)
        self.cancel_goal_button = QPushButton("Cancel Task")
        self.cancel_goal_button.setObjectName("Secondary")
        self.cancel_goal_button.clicked.connect(self._cancel_active_goal)
        self.block_goal_button = QPushButton("Block Task")
        self.block_goal_button.setObjectName("Danger")
        self.block_goal_button.clicked.connect(self._block_current_target)
        self.manual_complete_button = QPushButton("Mark Complete")
        self.manual_complete_button.setObjectName("GoldButton")
        self.manual_complete_button.clicked.connect(self._mark_active_complete)
        for button in [
            self.accept_goal_button, self.reroll_goal_button, self.cancel_goal_button,
            self.block_goal_button, self.manual_complete_button,
        ]:
            button.setMinimumHeight(36)
            action_row.addWidget(button)
        action_row.addStretch(1)
        goal_panel_layout.addLayout(action_row)
        hero_layout.addWidget(goal_panel)
        hero_layout.addStretch(1)
        main_row.addWidget(hero, 7)

        # ------------------------------------------------------------------
        # Right intelligence column - Account Overview + Lowest Skills.
        # ------------------------------------------------------------------
        right = QVBoxLayout()
        right.setSpacing(12)

        account_card = QFrame()
        account_card.setObjectName("DashboardCard")
        account_layout = QVBoxLayout(account_card)
        account_layout.setContentsMargins(14, 12, 14, 12)
        account_head = QHBoxLayout()
        account_heading = QLabel("Account Overview")
        account_heading.setObjectName("SectionTitle")
        self.account_title = QLabel("No account loaded")
        self.account_title.setObjectName("Muted")
        account_head.addWidget(account_heading)
        account_head.addStretch(1)
        account_head.addWidget(self.account_title)
        account_layout.addLayout(account_head)

        self.home_total_value = QLabel("-")
        self.home_combat_value = QLabel("-")
        self.home_xp_value = QLabel("-")
        self.home_collection_value = QLabel("-")
        self.home_account_type_value = QLabel("-")
        self.home_snapshot_value = QLabel("-")
        overview_values = [
            ("Total Level", self.home_total_value, "TL", "overview:total_level"),
            ("Combat Level", self.home_combat_value, "CB", "overview:combat_level"),
            ("Total XP", self.home_xp_value, "XP", "overview:total_xp"),
            ("Collections", self.home_collection_value, "CL", "overview:collections"),
            ("Account Type", self.home_account_type_value, "AT", "overview:account_type"),
            ("Snapshots", self.home_snapshot_value, "SN", "overview:snapshots"),
        ]
        self.home_overview_icons: dict[str, dict[str, object]] = {}
        stat_grid = QGridLayout()
        stat_grid.setSpacing(8)
        for index, (caption, value, glyph, asset_key) in enumerate(overview_values):
            tile = QFrame()
            tile.setObjectName("OverviewTile")
            tile_layout = QHBoxLayout(tile)
            tile_layout.setContentsMargins(9, 7, 9, 7)
            icon = QLabel(glyph)
            icon.setObjectName("OverviewGlyph")
            icon.setFixedSize(32, 32)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.home_overview_icons[asset_key] = {"label": icon, "fallback": glyph}
            copy = QVBoxLayout()
            copy.setSpacing(0)
            cap = QLabel(caption)
            cap.setObjectName("StatLabel")
            value.setObjectName("StatValue")
            copy.addWidget(cap)
            copy.addWidget(value)
            tile_layout.addWidget(icon)
            tile_layout.addLayout(copy, 1)
            stat_grid.addWidget(tile, index // 2, index % 2)
        account_layout.addLayout(stat_grid)
        self.account_summary = QLabel("Enter an RSN above to pull public HiScores data.")
        self.account_summary.setObjectName("Muted")
        self.account_summary.setWordWrap(True)
        account_layout.addWidget(self.account_summary)
        right.addWidget(account_card)

        skill_card = QFrame()
        skill_card.setObjectName("DashboardCard")
        skill_card.setMinimumHeight(250)
        skill_layout = QVBoxLayout(skill_card)
        skill_layout.setContentsMargins(14, 12, 14, 12)
        skill_head = QHBoxLayout()
        skill_title = QLabel("Lowest Skills")
        skill_title.setObjectName("SectionTitle")
        skill_head.addWidget(skill_title)
        skill_head.addStretch(1)
        lowest_hint = QLabel("live HiScores")
        lowest_hint.setObjectName("Muted")
        skill_head.addWidget(lowest_hint)
        skill_layout.addLayout(skill_head)
        # Keep these rows alive for the life of the window.  Earlier alphas
        # deleted/rebuilt the entire mini-panel whenever an asset finished
        # loading, which could leave the Home layout in a bad state on Windows.
        self.skill_box = QVBoxLayout()
        self.skill_box.setSpacing(5)
        self.lowest_skill_rows: list[dict[str, object]] = []
        for _ in range(5):
            row = QFrame()
            row.setObjectName("SkillRow")
            row.setMinimumHeight(36)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 3, 4, 3)
            row_layout.setSpacing(7)

            icon = QLabel()
            icon.setFixedSize(27, 27)
            name = QLabel("-")
            name.setMinimumWidth(88)
            level = QLabel("-")
            level.setObjectName("CardTitle")
            level.setFixedWidth(32)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)

            row_layout.addWidget(icon)
            row_layout.addWidget(name, 1)
            row_layout.addWidget(level)
            row_layout.addWidget(bar, 2)
            self.skill_box.addWidget(row)
            self.lowest_skill_rows.append({
                "row": row,
                "icon": icon,
                "name": name,
                "level": level,
                "bar": bar,
            })

        self.lowest_skills_empty = QLabel("Load an account to populate your lowest skills.")
        self.lowest_skills_empty.setObjectName("Muted")
        self.lowest_skills_empty.setWordWrap(True)
        self.skill_box.addWidget(self.lowest_skills_empty)
        # Attach the persistent skill-row layout to the card.  Alpha 6.6
        # created and updated these widgets correctly but never inserted their
        # layout into skill_layout, leaving the card visually empty.
        skill_layout.addLayout(self.skill_box, 1)
        right.addWidget(skill_card, 1)
        main_row.addLayout(right, 4)
        outer.addLayout(main_row)

        # ------------------------------------------------------------------
        # Bottom row mirrors mockup: long-term goal / recent progress /
        # playstyle insights.
        # ------------------------------------------------------------------
        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        path_card = QFrame()
        path_card.setObjectName("DashboardCard")
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(14, 12, 14, 12)
        path_head = QHBoxLayout()
        path_title = QLabel("Active Long-Term Goal")
        path_title.setObjectName("SectionTitle")
        view_paths = QPushButton("View Paths")
        view_paths.setObjectName("LinkButton")
        view_paths.clicked.connect(lambda: self._switch_page(2))
        path_head.addWidget(path_title)
        path_head.addStretch(1)
        path_head.addWidget(view_paths)
        path_layout.addLayout(path_head)
        self.home_path_name = QLabel("No active path")
        self.home_path_name.setObjectName("CardTitle")
        self.home_path_description = QLabel("Activate a long-term goal from the Paths tab.")
        self.home_path_description.setObjectName("Muted")
        self.home_path_description.setWordWrap(True)
        self.home_path_blocker = QLabel("Current blocker: -")
        self.home_path_blocker.setWordWrap(True)
        self.home_path_progress = QProgressBar()
        self.home_path_progress.setRange(0, 100)
        self.home_path_progress.setValue(0)
        path_layout.addWidget(self.home_path_name)
        path_layout.addWidget(self.home_path_description)
        path_layout.addWidget(self.home_path_blocker)
        path_layout.addWidget(self.home_path_progress)
        bottom.addWidget(path_card, 1)

        recent_card = QFrame()
        recent_card.setObjectName("DashboardCard")
        recent_layout = QVBoxLayout(recent_card)
        recent_layout.setContentsMargins(14, 12, 14, 12)
        recent_title = QLabel("Recent Progress")
        recent_title.setObjectName("SectionTitle")
        self.recent_progress_list = QListWidget()
        self.recent_progress_list.setMinimumHeight(150)
        recent_layout.addWidget(recent_title)
        recent_layout.addWidget(self.recent_progress_list)
        bottom.addWidget(recent_card, 1)

        insight_card = QFrame()
        insight_card.setObjectName("DashboardCard")
        insight_layout = QVBoxLayout(insight_card)
        insight_layout.setContentsMargins(14, 12, 14, 12)
        insight_title = QLabel("Playstyle Insights")
        insight_title.setObjectName("SectionTitle")
        self.home_playstyle_summary = QLabel("Use the generator to build playstyle analytics.")
        self.home_playstyle_summary.setWordWrap(True)
        self.home_playstyle_summary.setObjectName("Muted")
        completion_title = QLabel("Goal completion")
        completion_title.setObjectName("StatLabel")
        self.home_completion_progress = QProgressBar()
        self.home_completion_progress.setRange(0, 100)
        self.home_completion_progress.setValue(0)
        insight_layout.addWidget(insight_title)
        insight_layout.addWidget(self.home_playstyle_summary)
        insight_layout.addStretch(1)
        insight_layout.addWidget(completion_title)
        insight_layout.addWidget(self.home_completion_progress)
        bottom.addWidget(insight_card, 1)

        outer.addLayout(bottom)
        outer.addStretch(1)
        scroll.setWidget(page)
        return scroll

    def _build_bosses_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel("Bosses")
        title.setObjectName("Title")
        layout.addWidget(title)
        self.boss_note = QLabel(
            "All supported bosses are shown, including 0 KC. Goal targets use late-mid-game pace estimates."
        )
        self.boss_note.setObjectName("Muted")
        self.boss_note.setWordWrap(True)
        layout.addWidget(self.boss_note)

        controls = QFrame()
        controls.setObjectName("Card")
        controls_layout = QHBoxLayout(controls)
        self.boss_search_input = QLineEdit()
        self.boss_search_input.setPlaceholderText("Search bosses...")
        self.boss_filter_combo = QComboBox()
        self.boss_filter_combo.addItems([
            "All Bosses", "Favorites", "0 KC", "Has KC", "Targetable", "Special"
        ])
        self.boss_difficulty_combo = QComboBox()
        self.boss_difficulty_combo.addItems(["Chill", "Moderate", "Grind"])
        self.boss_difficulty_combo.setCurrentIndex(1)
        self.boss_session_combo = QComboBox()
        self.boss_session_combo.addItem("15 Minutes", 15)
        self.boss_session_combo.addItem("30 Minutes", 30)
        self.boss_session_combo.addItem("1 Hour", 60)
        self.boss_session_combo.addItem("2+ Hours", 120)
        self.boss_session_combo.setCurrentIndex(2)
        controls_layout.addWidget(self.boss_search_input, 2)
        controls_layout.addWidget(self.boss_filter_combo, 1)
        controls_layout.addWidget(self.boss_difficulty_combo, 1)
        controls_layout.addWidget(self.boss_session_combo, 1)
        layout.addWidget(controls)

        self.boss_search_input.textChanged.connect(lambda *_: self._render_bosses())
        self.boss_filter_combo.currentIndexChanged.connect(lambda *_: self._render_bosses())
        self.boss_difficulty_combo.currentIndexChanged.connect(lambda *_: self._render_bosses())
        self.boss_session_combo.currentIndexChanged.connect(lambda *_: self._render_bosses())

        self.boss_table = QTableWidget(0, 7)
        self.boss_table.setHorizontalHeaderLabels([
            "Favorite", "Boss / Activity", "KC", "Late-mid / h", "Session Target", "Goal", "Details"
        ])
        self.boss_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.boss_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.boss_table.setAlternatingRowColors(True)
        self.boss_table.setShowGrid(False)
        # Boss sprites are bundled from the compact RuneLite HiScores grid.
        # Preserve their pixel-art scale rather than substituting large boss art.
        self.boss_table.setIconSize(QSize(25, 25))
        self.boss_table.verticalHeader().setVisible(False)
        self.boss_table.verticalHeader().setMinimumSectionSize(62)
        self.boss_table.verticalHeader().setDefaultSectionSize(62)

        header = self.boss_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.boss_table.setColumnWidth(0, 112)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

        # QHeaderView.ResizeToContents does not reliably account for a QWidget
        # placed inside a QTableWidget cell on all DPI/font combinations. The
        # old Goal column could therefore be narrower than its button. Reserve
        # a real action column instead of hoping Qt infers the widget width.
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.boss_table.setColumnWidth(5, 188)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.boss_table.setColumnWidth(6, 106)
        layout.addWidget(self.boss_table, 1)
        return page

    # ------------------------------------------------------------------
    # Progression Paths
    # ------------------------------------------------------------------

    def _build_paths_page(self) -> QWidget:
        """Card-based path page.

        Table cell widgets caused repeated height/overlap regressions. Alpha 6.1
        moves every action into a dedicated card footer, which also matches the
        approved GUI mockup better.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(12)

        head = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Progression Paths")
        title.setObjectName("Title")
        note = QLabel(
            "Build long-term goals, see the next measurable blocker, and turn that blocker into a session task. "
            "Completed paths disappear automatically."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(note)
        head.addLayout(title_box, 1)
        self.create_path_button = QPushButton("+ Create Custom Path")
        self.create_path_button.setObjectName("Primary")
        self.create_path_button.setMinimumHeight(38)
        self.create_path_button.clicked.connect(self._create_custom_path)
        head.addWidget(self.create_path_button, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(head)

        path_scroll = QScrollArea()
        path_scroll.setWidgetResizable(True)
        host = QWidget()
        self.paths_cards_layout = QVBoxLayout(host)
        self.paths_cards_layout.setContentsMargins(0, 2, 0, 2)
        self.paths_cards_layout.setSpacing(10)
        self.paths_cards_layout.addStretch(1)
        path_scroll.setWidget(host)
        layout.addWidget(path_scroll, 1)
        return page

    def _build_diaries_page(self) -> QWidget:
        """Card-based Achievement Diary readiness page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(12)

        title = QLabel("Achievement Diary Readiness")
        title.setObjectName("Title")
        layout.addWidget(title)
        self.diary_note = QLabel(
            "Quest prerequisites are assumed complete. Skill and supported boss requirements are checked "
            "against your account; diary completion itself is confirmed manually."
        )
        self.diary_note.setObjectName("Muted")
        self.diary_note.setWordWrap(True)
        layout.addWidget(self.diary_note)

        controls = QFrame()
        controls.setObjectName("TopStatStrip")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(12, 8, 12, 8)
        self.diary_region_combo = QComboBox()
        self.diary_region_combo.addItem("All Regions")
        self.diary_tier_combo = QComboBox()
        self.diary_tier_combo.addItems(["All Tiers", "Easy", "Medium", "Hard", "Elite"])
        self.diary_tracked_combo = QComboBox()
        self.diary_tracked_combo.addItems(["All Incomplete", "Tracked Only", "Stats Ready"])
        self.diary_refresh_button = QPushButton("Refresh Requirements")
        self.diary_refresh_button.setObjectName("Secondary")
        self.diary_refresh_button.setMinimumHeight(34)
        self.diary_refresh_button.clicked.connect(self._refresh_diary_requirements)
        controls_layout.addWidget(self.diary_region_combo, 2)
        controls_layout.addWidget(self.diary_tier_combo, 1)
        controls_layout.addWidget(self.diary_tracked_combo, 1)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.diary_refresh_button)
        layout.addWidget(controls)

        self.diary_region_combo.currentIndexChanged.connect(lambda *_: self._render_diaries())
        self.diary_tier_combo.currentIndexChanged.connect(lambda *_: self._render_diaries())
        self.diary_tracked_combo.currentIndexChanged.connect(lambda *_: self._render_diaries())

        diary_scroll = QScrollArea()
        diary_scroll.setWidgetResizable(True)
        host = QWidget()
        self.diary_cards_layout = QVBoxLayout(host)
        self.diary_cards_layout.setContentsMargins(0, 2, 0, 2)
        self.diary_cards_layout.setSpacing(10)
        self.diary_cards_layout.addStretch(1)
        diary_scroll.setWidget(host)
        layout.addWidget(diary_scroll, 1)
        return page

    def _build_collection_page(self) -> QWidget:
        """Verified overall Collection Log score + manual tracked grinds.

        Public HiScores expose the overall Collections Logged value, but not the
        identity of missing slots. Alpha 7 keeps that boundary explicit: the
        overall count is automatic while source-specific grinds are local/manual.
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(12)

        head = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Collection Log")
        title.setObjectName("Title")
        note = QLabel(
            "Overall Collections Logged is verified from public HiScores. When the RuneLite companion is connected, "
            "Collection Log pages you open in-game are synced locally with exact obtained/missing item IDs."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(note)
        head.addLayout(title_box, 1)
        self.collection_generate_button = QPushButton("Generate Collection Goal")
        self.collection_generate_button.setObjectName("Primary")
        self.collection_generate_button.clicked.connect(self._generate_collection_goal)
        head.addWidget(self.collection_generate_button)
        self.collection_add_button = QPushButton("+ Track Grind")
        self.collection_add_button.setObjectName("Secondary")
        self.collection_add_button.clicked.connect(self._add_collection_target)
        head.addWidget(self.collection_add_button)
        layout.addLayout(head)

        stats = QFrame()
        stats.setObjectName("TopStatStrip")
        grid = QGridLayout(stats)
        grid.setContentsMargins(14, 10, 14, 10)
        self.collection_overall_value = QLabel("-")
        self.collection_gain_value = QLabel("-")
        self.collection_tracked_value = QLabel("-")
        self.collection_slots_value = QLabel("-")
        self.collection_runelite_value = QLabel("-")
        for col, (label, value) in enumerate([
            ("Collections Logged", self.collection_overall_value),
            ("Observed Gain", self.collection_gain_value),
            ("RuneLite Pages", self.collection_runelite_value),
            ("Tracked Grinds", self.collection_tracked_value),
            ("Manual Slots", self.collection_slots_value),
        ]):
            value.setObjectName("CardTitle")
            grid.addWidget(QLabel(label), 0, col)
            grid.addWidget(value, 1, col)
        layout.addWidget(stats)

        controls = QFrame()
        controls.setObjectName("TopStatStrip")
        row = QHBoxLayout(controls)
        row.setContentsMargins(12, 8, 12, 8)
        self.collection_search = QLineEdit()
        self.collection_search.setPlaceholderText("Search synced pages and tracked grinds...")
        self.collection_category = QComboBox()
        self.collection_category.addItems(["All Categories", *CATEGORIES])
        self.collection_category.setToolTip("Filter synced pages and manual grinds. Unmapped synced pages appear under Uncategorized.")
        self.collection_status = QComboBox()
        self.collection_status.addItems(["Incomplete", "All", "Completed"])
        row.addWidget(self.collection_search, 2)
        row.addWidget(self.collection_category, 1)
        row.addWidget(self.collection_status, 1)
        layout.addWidget(controls)
        self.collection_search.textChanged.connect(lambda *_: self._render_collection())
        self.collection_category.currentIndexChanged.connect(lambda *_: self._render_collection())
        self.collection_status.currentIndexChanged.connect(lambda *_: self._render_collection())

        host = QWidget()
        self.collection_cards_layout = QVBoxLayout(host)
        self.collection_cards_layout.setContentsMargins(0, 2, 0, 2)
        self.collection_cards_layout.setSpacing(10)
        self.collection_cards_layout.addStretch(1)
        layout.addWidget(host, 1)
        scroll.setWidget(page)
        return scroll

    def _build_stats_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(14)

        title = QLabel("Stats & Analytics")
        title.setObjectName("Title")
        layout.addWidget(title)
        note = QLabel(
            "Built only from snapshots and tasks this app has actually observed. "
            "No estimated playtime or invented account history."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        summary_row = QHBoxLayout()
        self.stats_tracking = QLabel("Snapshots\n-")
        self.stats_xp = QLabel("XP Gained\n-")
        self.stats_levels = QLabel("Levels Gained\n-")
        self.stats_completion = QLabel("Task Completion\n-")
        for label in [self.stats_tracking, self.stats_xp, self.stats_levels, self.stats_completion]:
            card = QFrame()
            card.setObjectName("Card")
            card_layout = QVBoxLayout(card)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            card_layout.addWidget(label)
            summary_row.addWidget(card, 1)
        layout.addLayout(summary_row)

        tables_row = QHBoxLayout()
        skill_card = QFrame()
        skill_card.setObjectName("Card")
        skill_layout = QVBoxLayout(skill_card)
        skill_title = QLabel("Top Skill Gains")
        skill_title.setObjectName("SectionTitle")
        self.stats_skill_table = QTableWidget(0, 3)
        self.stats_skill_table.setHorizontalHeaderLabels(["Skill", "XP Gained", "Levels"])
        self.stats_skill_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stats_skill_table.setAlternatingRowColors(True)
        self.stats_skill_table.setShowGrid(False)
        self.stats_skill_table.verticalHeader().setVisible(False)
        self.stats_skill_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.stats_skill_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.stats_skill_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        skill_layout.addWidget(skill_title)
        skill_layout.addWidget(self.stats_skill_table)

        activity_card = QFrame()
        activity_card.setObjectName("Card")
        activity_layout = QVBoxLayout(activity_card)
        activity_title = QLabel("Top Activity / Boss Gains")
        activity_title.setObjectName("SectionTitle")
        self.stats_activity_table = QTableWidget(0, 2)
        self.stats_activity_table.setHorizontalHeaderLabels(["Activity", "Gain"])
        self.stats_activity_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stats_activity_table.setAlternatingRowColors(True)
        self.stats_activity_table.setShowGrid(False)
        self.stats_activity_table.verticalHeader().setVisible(False)
        self.stats_activity_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.stats_activity_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        activity_layout.addWidget(activity_title)
        activity_layout.addWidget(self.stats_activity_table)

        tables_row.addWidget(skill_card, 1)
        tables_row.addWidget(activity_card, 1)
        layout.addLayout(tables_row)

        goal_card = QFrame()
        goal_card.setObjectName("Card")
        goal_layout = QVBoxLayout(goal_card)
        goal_title = QLabel("Goal Performance")
        goal_title.setObjectName("SectionTitle")
        self.stats_goal_summary = QLabel("No tracked tasks yet.")
        self.stats_goal_summary.setWordWrap(True)
        goal_layout.addWidget(goal_title)
        goal_layout.addWidget(self.stats_goal_summary)
        layout.addWidget(goal_card)

        layout.addStretch(1)
        scroll.setWidget(page)
        return scroll

    # ------------------------------------------------------------------
    # History / settings
    # ------------------------------------------------------------------

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel("Goal History")
        title.setObjectName("Title")
        layout.addWidget(title)
        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels([
            "Accepted", "Goal", "Category", "Status", "Progress", "Score"
        ])
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setShowGrid(False)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.history_table, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel("Settings")
        title.setObjectName("Title")
        layout.addWidget(title)
        note = QLabel(
            "Account-specific settings are stored locally. Alpha 8 can also read live account data from the local RuneLite companion bridge."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        cards = QHBoxLayout()

        blocked_card = QFrame()
        blocked_card.setObjectName("Card")
        blocked_layout = QVBoxLayout(blocked_card)
        blocked_title = QLabel("Blocked Targets")
        blocked_title.setObjectName("SectionTitle")
        self.blocked_list = QListWidget()
        unblock = QPushButton("Unblock Selected")
        unblock.setObjectName("Secondary")
        unblock.clicked.connect(self._unblock_selected)
        blocked_layout.addWidget(blocked_title)
        blocked_layout.addWidget(self.blocked_list)
        blocked_layout.addWidget(unblock)

        diary_card = QFrame()
        diary_card.setObjectName("Card")
        diary_layout = QVBoxLayout(diary_card)
        diary_title = QLabel("Completed Diaries")
        diary_title.setObjectName("SectionTitle")
        self.completed_diary_list = QListWidget()
        restore_diary = QPushButton("Restore Selected Diary")
        restore_diary.setObjectName("Secondary")
        restore_diary.clicked.connect(self._restore_selected_diary)
        diary_layout.addWidget(diary_title)
        diary_layout.addWidget(self.completed_diary_list)
        diary_layout.addWidget(restore_diary)

        cards.addWidget(blocked_card, 1)
        cards.addWidget(diary_card, 1)
        layout.addLayout(cards, 1)

        memory_card = QFrame()
        memory_card.setObjectName("Card")
        memory_layout = QVBoxLayout(memory_card)
        memory_title = QLabel("Recommendation Memory")
        memory_title.setObjectName("SectionTitle")
        memory_note = QLabel(
            "Rerolled targets are remembered temporarily so the generator does not immediately repeat them. "
            "Clear this memory whenever you want a completely fresh recommendation pool."
        )
        memory_note.setObjectName("Muted")
        memory_note.setWordWrap(True)
        self.reroll_memory_label = QLabel("Reroll memory: load an account")
        self.reroll_memory_label.setObjectName("Muted")
        clear_rerolls = QPushButton("Clear Reroll Memory")
        clear_rerolls.setObjectName("Secondary")
        clear_rerolls.setMinimumHeight(38)
        clear_rerolls.clicked.connect(self._clear_reroll_memory)
        memory_layout.addWidget(memory_title)
        memory_layout.addWidget(memory_note)
        memory_layout.addWidget(self.reroll_memory_label)
        memory_layout.addWidget(clear_rerolls, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(memory_card)

        bridge_card = QFrame()
        bridge_card.setObjectName("Card")
        bridge_layout = QVBoxLayout(bridge_card)
        bridge_title = QLabel("RuneLite Companion")
        bridge_title.setObjectName("SectionTitle")
        bridge_note = QLabel(
            "The companion writes a local sync file only. No server, account password, or Jagex session token is used. "
            "Open Collection Log pages in RuneLite to teach the desktop app their exact obtained/missing entries."
        )
        bridge_note.setObjectName("Muted")
        bridge_note.setWordWrap(True)
        self.runelite_bridge_status = QLabel("RuneLite companion: not detected")
        self.runelite_bridge_status.setObjectName("CardTitle")
        self.runelite_bridge_path = QLabel(str(self.runelite_sync_service.path))
        self.runelite_bridge_path.setObjectName("Muted")
        self.runelite_bridge_path.setWordWrap(True)
        self.runelite_bridge_detail = QLabel("Synced Collection Log pages: 0")
        self.runelite_bridge_detail.setObjectName("Muted")
        refresh_bridge = QPushButton("Refresh RuneLite Bridge")
        refresh_bridge.setObjectName("Secondary")
        refresh_bridge.clicked.connect(self._poll_runelite_sync)
        bridge_layout.addWidget(bridge_title)
        bridge_layout.addWidget(bridge_note)
        bridge_layout.addWidget(self.runelite_bridge_status)
        bridge_layout.addWidget(self.runelite_bridge_path)
        bridge_layout.addWidget(self.runelite_bridge_detail)
        bridge_layout.addWidget(refresh_bridge, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(bridge_card)
        return page

    def _placeholder_page(self, title_text: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 22)
        title = QLabel(title_text)
        title.setObjectName("Title")
        note = QLabel(
            "Planned screen - this navigation slot is reserved for a later alpha rather than filled with fake data."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # RuneLite companion bridge
    # ------------------------------------------------------------------

    def _refresh_runelite_snapshot(self) -> RuneLiteSyncSnapshot | None:
        self.runelite_snapshot = self.runelite_sync_service.load()
        return self.runelite_snapshot

    def _runelite_is_live_for_profile(self, profile: PlayerProfile | None = None) -> bool:
        profile = profile or self.session.profile
        snapshot = self.runelite_snapshot
        return bool(snapshot and snapshot.is_fresh() and snapshot.matches(profile)
                    and snapshot.game_state == "LOGGED_IN")

    def _poll_runelite_sync(self) -> None:
        snapshot = self._refresh_runelite_snapshot()
        fingerprint = self.runelite_sync_service.fingerprint(snapshot)
        previous_fingerprint = self.runelite_fingerprint
        self.runelite_fingerprint = fingerprint

        profile = self.session.profile
        live = bool(profile and self.progress_service.is_live(snapshot, profile))
        changed = fingerprint != previous_fingerprint or live != getattr(self, "runelite_was_live", False)
        self.runelite_was_live = live
        if self.pages.currentIndex() == 7:
            self._render_settings()
        if live:
            # Merge only live skill/XP values. Boss/activity values continue to
            # come from HiScores in Alpha 8.
            merged = self.runelite_sync_service.merge_profile(profile, snapshot)
            self.session.profile = merged

            active = self.store.active_goal(self.state, merged)
            completed_goal = None
            if active and (active.subtype == "collection_slot" or
                           (active.subtype in {"skill_xp", "skill_level"} and active.target_name in snapshot.skills)):
                before = active.to_dict()
                result = self.progress_service.apply(active, merged, snapshot)
                if active.to_dict() != before:
                    self.store.update_active_goal(self.state, merged, active)
                    if result.completed:
                        completed_goal = active
                        self.store.archive_active_goal(self.state, merged, "completed")
                    self.store.save(self.state)

            if changed:
                self._render_all()
            else:
                self._render_topbar()
                if self.pages.currentIndex() == 0:
                    self._render_goal_panel()
            if completed_goal:
                QMessageBox.information(
                    self, APP_NAME,
                    f"Goal complete from live RuneLite data!\n\n{completed_goal.title}\n{completed_goal.objective}",
                )
            return

        # A stale/mismatched bridge should still update the status UI.
        self._render_topbar()
        if self.pages.currentIndex() == 0:
            self._render_goal_panel()
        if changed:
            if self.pages.currentIndex() == 4:
                self._render_collection()
            if self.pages.currentIndex() == 7:
                self._render_settings()

    # ------------------------------------------------------------------
    # Account loading / snapshots
    # ------------------------------------------------------------------

    def _restore_last_account(self) -> None:
        last = self.state.get("last_account") or {}
        rsn = last.get("rsn")
        account_type = last.get("account_type", "normal")
        if not rsn:
            return

        self.rsn_input.setText(rsn)
        index = self.account_type.findData(account_type)
        if index >= 0:
            self.account_type.setCurrentIndex(index)

        cached = self.store.latest_profile(self.state, rsn, account_type)
        if cached:
            self.session.profile = cached
            self.session.previous_profile = None
            self._render_all()

    def _load_account(self) -> None:
        rsn = self.rsn_input.text().strip()
        if not rsn:
            QMessageBox.warning(self, APP_NAME, "Enter a RuneScape name first.")
            return
        account_type = self.account_type.currentData()
        self.load_button.setEnabled(False)
        self.load_button.setText("Loading...")
        self.top_refresh_button.setEnabled(False)
        self.top_refresh_button.setText("Refreshing...")
        self.fetch_thread = QThread(self)
        worker = FetchWorker(rsn, account_type)
        worker.moveToThread(self.fetch_thread)
        self.fetch_thread.started.connect(worker.run)
        worker.finished.connect(self._profile_loaded)
        worker.failed.connect(self._profile_failed)
        worker.finished.connect(self.fetch_thread.quit)
        worker.failed.connect(self.fetch_thread.quit)
        self.fetch_thread.finished.connect(worker.deleteLater)
        self.fetch_thread.finished.connect(self.fetch_thread.deleteLater)
        self.fetch_thread.start()
        self._worker = worker

    def _profile_loaded(self, profile: PlayerProfile) -> None:
        self.load_button.setEnabled(True)
        self.load_button.setText("Load / Refresh Account")
        self.top_refresh_button.setEnabled(True)
        self.top_refresh_button.setText("Refresh")

        previous = self.store.latest_profile(
            self.state,
            profile.rsn,
            profile.account_type,
        )
        self.session.previous_profile = previous
        self.session.profile = profile
        self.session.current_goal = None
        self.store.save_profile(self.state, profile)

        # Overlay fresher local RuneLite skill/XP data in memory when the
        # companion is connected to this same account. Activities remain from
        # public HiScores for Alpha 8.
        self._refresh_runelite_snapshot()
        if self.runelite_snapshot and self.runelite_snapshot.is_fresh() and self.runelite_snapshot.matches(profile):
            self.session.profile = self.runelite_sync_service.merge_profile(profile, self.runelite_snapshot)
            profile = self.session.profile

        completed_goal: Goal | None = None
        active = self.store.active_goal(self.state, profile)
        if active:
            result = self.progress_service.apply(active, profile, self.runelite_snapshot)
            self.store.update_active_goal(self.state, profile, active)
            if result.completed:
                completed_goal = active
                self.store.archive_active_goal(self.state, profile, "completed")

        self.store.save(self.state)
        self._render_all()

        if completed_goal:
            QMessageBox.information(
                self,
                APP_NAME,
                f"Goal complete!\n\n{completed_goal.title}\n{completed_goal.objective}",
            )

    def _profile_failed(self, message: str) -> None:
        self.load_button.setEnabled(True)
        self.load_button.setText("Load / Refresh Account")
        self.top_refresh_button.setEnabled(True)
        self.top_refresh_button.setText("Refresh")
        self._render_topbar()
        QMessageBox.critical(self, APP_NAME, message)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _sync_progression_sources(self, *, load_diaries: bool = False) -> None:
        profile = self.session.profile
        if profile is None:
            self.progression_service.set_custom_paths([])
            self.progression_service.set_external_paths([])
            return

        self.progression_service.set_custom_paths(
            self.store.custom_paths(self.state, profile)
        )

        needs_diaries = bool(self.store.active_diaries(self.state, profile))
        if (load_diaries or needs_diaries) and not self.diary_definitions:
            self._load_diary_definitions()

        diary_paths = [
            self.diary_service.as_path(diary)
            for diary in self.diary_definitions
        ]
        self.progression_service.set_external_paths(diary_paths)

    def _combined_active_specs(self) -> list[dict]:
        profile = self.session.profile
        if profile is None:
            return []
        specs = list(self.store.active_paths(self.state, profile))
        completed = self.store.completed_diaries(self.state, profile)
        for spec in self.store.active_diaries(self.state, profile):
            diary_id = str(spec.get("diary_id", ""))
            if diary_id and diary_id not in completed:
                specs.append({
                    "path_id": f"diary:{diary_id}",
                    "priority": spec.get("priority", "medium"),
                })
        return specs

    def _render_all(self) -> None:
        self._render_topbar()
        self._sync_progression_sources(load_diaries=False)
        self._prune_completed_active_paths()
        self._render_home()
        self._render_progress()
        self._render_bosses()
        self._render_paths()
        profile = self.session.profile
        should_render_diaries = bool(
            self.diary_definitions
            or self.pages.currentIndex() == 3
            or (profile is not None and self.store.active_diaries(self.state, profile))
        )
        if should_render_diaries:
            self._render_diaries()
        self._render_collection()
        self._render_stats()
        self._render_history()
        self._render_settings()

    def _prune_completed_active_paths(self) -> None:
        profile = self.session.profile
        if profile is None:
            return
        changed = False
        for spec in list(self.store.active_paths(self.state, profile)):
            path = self.progression_service.definition(str(spec.get("path_id", "")))
            if path and self.progression_service.path_is_complete(path, profile):
                self.store.deactivate_path(self.state, profile, path.path_id)
                changed = True
        if changed:
            self.store.save(self.state)

    def _render_overview_icons(self) -> list[str]:
        missing: list[str] = []
        for key, record in getattr(self, "home_overview_icons", {}).items():
            label = record["label"]
            fallback = str(record["fallback"])
            path = self._asset_path(key)
            if path:
                label.setText("")
                self._set_pixmap(label, path, 26)
            else:
                label.clear()
                label.setText(fallback)
                if self.asset_service.can_fetch(key):
                    missing.append(key)
        return missing

    def _render_home(self) -> None:
        profile = self.session.profile
        overview_asset_keys = self._render_overview_icons()
        if profile is None:
            self.account_title.setText("No account loaded")
            self.home_total_value.setText("-")
            self.home_combat_value.setText("-")
            self.home_xp_value.setText("-")
            self.home_collection_value.setText("-")
            self.home_account_type_value.setText("-")
            self.home_snapshot_value.setText("-")
            self.lowest_skills_empty.setText("Load an account to populate your lowest skills.")
            self.lowest_skills_empty.setVisible(True)
            for widgets in self.lowest_skill_rows:
                widgets["row"].setVisible(False)
            self.home_path_name.setText("No active path")
            self.home_path_description.setText("Activate a long-term goal from the Paths tab.")
            self.home_path_blocker.setText("Current blocker: -")
            self.home_path_progress.setValue(0)
            self.home_playstyle_summary.setText("Use the generator to build playstyle analytics.")
            self.home_completion_progress.setValue(0)
            self._request_assets(overview_asset_keys)
            self._render_goal_panel()
            return

        overall = profile.overall
        combat = combat_level(profile)
        snapshots = self.store.snapshots(self.state, profile)
        collection = profile.activity("Collections Logged")
        collection_value = max(0, collection.score) if collection and collection.score >= 0 else None

        self.account_title.setText(profile.rsn)
        self.home_total_value.setText(str(overall.level) if overall else "-")
        self.home_combat_value.setText(str(combat if combat is not None else "-"))
        self.home_xp_value.setText(f"{overall.xp:,}" if overall else "-")
        self.home_collection_value.setText(f"{collection_value:,}" if collection_value is not None else "Not ranked")
        self.home_account_type_value.setText(ACCOUNT_LABELS.get(profile.account_type, profile.account_type))
        self.home_snapshot_value.setText(str(len(snapshots)))
        if self._runelite_is_live_for_profile(profile):
            age = self.runelite_snapshot.age_seconds() if self.runelite_snapshot else None
            age_text = f"{int(age)}s ago" if age is not None else "now"
            self.account_summary.setText(f"RuneLite live - updated {age_text} | HiScores baseline: {profile.fetched_at}")
        else:
            self.account_summary.setText(f"HiScores last synced: {profile.fetched_at}")

        asset_keys: list[str] = list(overview_asset_keys)
        skills = lowest_skills(profile, 5)
        self.lowest_skills_empty.setVisible(not bool(skills))
        if not skills:
            self.lowest_skills_empty.setText("No skill data is available for this account.")

        for index, widgets in enumerate(self.lowest_skill_rows):
            row = widgets["row"]
            icon = widgets["icon"]
            name = widgets["name"]
            level = widgets["level"]
            bar = widgets["bar"]
            if index >= len(skills):
                row.setVisible(False)
                continue

            skill = skills[index]
            row.setVisible(True)
            icon.clear()
            key = f"skill:{skill.name}"
            path = self._asset_path(key)
            if path:
                self._set_pixmap(icon, path, 25)
            else:
                asset_keys.append(key)
            name.setText(skill.name)
            level.setText(str(skill.level))
            bar.setValue(int((level_progress(skill) or 0) * 100))

        active_specs = self._combined_active_specs()
        evaluations = self.progression_service.evaluate_active_paths(profile, active_specs)
        if not evaluations:
            self.home_path_name.setText("No active path")
            self.home_path_description.setText("Activate a long-term goal from the Paths tab.")
            self.home_path_blocker.setText("Current blocker: -")
            self.home_path_progress.setValue(0)
        else:
            evaluation = sorted(
                evaluations,
                key=lambda item: ({"critical": 4, "high": 3, "medium": 2, "low": 1}.get(item.priority, 0), -item.progress_percent),
                reverse=True,
            )[0]
            blocker = evaluation.current_blocker
            self.home_path_name.setText(f"{evaluation.path.name}   |   {evaluation.priority.title()}")
            self.home_path_description.setText(evaluation.path.description or "Active progression goal")
            blocker_text = self._format_requirement_status(blocker) if blocker else "No measurable blocker"
            self.home_path_blocker.setText(f"Current blocker: {blocker_text}")
            self.home_path_progress.setValue(int(evaluation.progress_percent))

        analytics = self.analytics_service.summarize(
            snapshots,
            self.store.goal_history(self.state, profile),
            self.store.active_goal(self.state, profile),
        )
        prefs = self.store.preferences(self.state, profile)
        rerolls = list(prefs.get("rerolled_targets", []))
        most_rerolled = "-"
        if rerolls:
            from collections import Counter
            most_rerolled = Counter(rerolls).most_common(1)[0][0]
        favorite = analytics.favorite_category.title() if analytics.favorite_category else "-"
        strongest = analytics.strongest_category.title() if analytics.strongest_category else "-"
        outcomes = analytics.completed_tasks + analytics.cancelled_tasks + analytics.blocked_tasks
        completion = analytics.completion_rate if outcomes else 0.0
        self.home_playstyle_summary.setText(
            f"Favorite category:  {favorite}\n"
            f"Highest completion:  {strongest}\n"
            f"Most rerolled target:  {most_rerolled}\n"
            f"Tracked snapshots:  {analytics.snapshot_count}"
        )
        self.home_completion_progress.setValue(int(completion))

        self._request_assets(asset_keys)
        self._render_goal_panel()

    def _render_goal_panel(self) -> None:
        profile = self.session.profile
        active = self.store.active_goal(self.state, profile) if profile else None

        has_account = profile is not None
        controls = [self.category_combo, self.difficulty_combo, self.session_combo]

        if active is not None and profile is not None:
            self._render_goal_icon(active)
            result = self.progress_service.evaluate(active, profile, self.runelite_snapshot)
            self.goal_mode_label.setText("ACTIVE TASK")
            self.goal_title.setText(active.title)
            self.goal_objective.setText(active.objective)
            self.goal_reasons.setText("\n".join(f" |  {reason}" for reason in active.reasons) or " |  Accepted task")
            self.goal_bonus.setText(f"BONUS\n{active.bonus}" if active.bonus else "")
            self.goal_score_hint.setText(
                f"{active.category.title()}  |  {active.metadata.get('difficulty', '').title()}  |  "
                f"{active.estimated_minutes or '-'} min"
            )
            self.home_active_progress.setVisible(True)
            self.home_active_progress.setValue(int(result.progress_percent))
            if result.verifiable:
                self.home_active_status.setText(
                    f"{result.source}  |  {result.progress_percent:.0f}% complete  |  {result.label}"
                )
            else:
                self.home_active_status.setText(
                    f"{result.source}: {result.label}" if active.subtype == "collection_slot"
                    else "This task requires manual completion confirmation."
                )

            for control in controls:
                control.setEnabled(False)
            self.generate_button.setEnabled(False)
            self.generate_button.setText("Task Active")
            self.accept_goal_button.setVisible(False)
            self.reroll_goal_button.setVisible(False)
            self.cancel_goal_button.setVisible(True)
            self.block_goal_button.setVisible(True)
            self.manual_complete_button.setVisible(not result.verifiable and active.subtype != "collection_slot")
            return

        for control in controls:
            control.setEnabled(has_account)
        self.generate_button.setEnabled(has_account)
        self.generate_button.setText("GENERATE GOAL")
        self.home_active_progress.setVisible(False)
        self.home_active_progress.setValue(0)
        self.home_active_status.setText("")
        self.cancel_goal_button.setVisible(False)
        self.manual_complete_button.setVisible(False)

        goal = self.session.current_goal
        if goal is None:
            self._render_goal_icon(None)
            self.goal_mode_label.setText("READY" if has_account else "LOAD AN ACCOUNT")
            self.goal_title.setText("No goal generated yet")
            self.goal_objective.setText(
                "Choose your filters and generate a task." if has_account
                else "Load an account above to begin."
            )
            self.goal_reasons.setText("-")
            self.goal_bonus.setText("")
            self.goal_score_hint.setText("")
            self.accept_goal_button.setVisible(False)
            self.reroll_goal_button.setVisible(False)
            self.block_goal_button.setVisible(False)
            return

        self._render_goal_icon(goal)
        self.goal_mode_label.setText("RECOMMENDATION")
        self.goal_title.setText(goal.title)
        self.goal_objective.setText(goal.objective)
        self.goal_reasons.setText("\n".join(f" |  {reason}" for reason in goal.reasons))
        self.goal_bonus.setText(f"BONUS\n{goal.bonus}" if goal.bonus else "")
        self.goal_score_hint.setText(
            f"Recommendation score: {goal.score:.0f}  |  {goal.category.title()}  |  "
            f"{goal.metadata.get('difficulty', '').title()}  |  {goal.estimated_minutes or '-'} min"
        )
        self.accept_goal_button.setVisible(True)
        self.reroll_goal_button.setVisible(True)
        self.block_goal_button.setVisible(True)

    def _render_progress(self) -> None:
        """Render the compact Recent Progress card used by the mockup Home."""
        if not hasattr(self, "recent_progress_list"):
            return
        profile = self.session.profile
        self.recent_progress_list.clear()
        if profile is None:
            self.recent_progress_list.addItem("Load an account to track progress.")
            return

        changes = compare_profiles(self.session.previous_profile, profile)
        lines: list[str] = []
        for change in changes["skills"][:4]:
            suffix = ""
            if change["new_level"] > change["old_level"]:
                suffix = f"  |  {change['old_level']} -> {change['new_level']}"
            lines.append(f"+{change['xp_delta']:,} {change['name']} XP{suffix}")
        for change in changes["activities"][:3]:
            lines.append(f"+{change['delta']} {change['name']} ({change['old']} -> {change['new']})")

        if not lines:
            history = list(reversed(self.store.goal_history(self.state, profile)))
            for goal in history[:5]:
                lines.append(f"{goal.title}  |  {goal.status.title()}")
        if not lines:
            lines.append("Refresh after playing to build recent progress.")
        for line in lines[:7]:
            self.recent_progress_list.addItem(line)

    def _render_bosses(self) -> None:
        profile = self.session.profile
        self.boss_table.setRowCount(0)
        if profile is None:
            self.boss_note.setText("Load an account to see boss KC and session-scaled targets.")
            return

        difficulty = self.boss_difficulty_combo.currentText().lower()
        minutes = int(self.boss_session_combo.currentData())
        query = self.boss_search_input.text().strip().lower()
        filter_name = self.boss_filter_combo.currentText()
        favorites = self.store.favorite_bosses(self.state, profile)

        visible: list[str] = []
        for name in sorted(all_boss_names(), key=str.casefold):
            rate = boss_rate(name)
            activity = profile.activity(name)
            current = max(0, activity.score) if activity else 0

            if query and query not in name.lower():
                continue
            if filter_name == "Favorites" and name not in favorites:
                continue
            if filter_name == "0 KC" and current != 0:
                continue
            if filter_name == "Has KC" and current <= 0:
                continue
            if filter_name == "Targetable" and (rate is None or not rate.targetable):
                continue
            if filter_name == "Special" and (rate is None or rate.targetable):
                continue
            visible.append(name)

        self.boss_note.setText(
            f"Showing {len(visible)} of {len(all_boss_names())} supported bosses/activities. "
            f"Targets: {difficulty.title()}  |  {minutes} min. "
            "Use Saved to keep bosses in your Favorites filter."
        )

        asset_keys: list[str] = []
        self.boss_table.setRowCount(len(visible))
        for row, name in enumerate(visible):
            self.boss_table.setRowHeight(row, 62)
            rate = boss_rate(name)
            activity = profile.activity(name)
            current = max(0, activity.score) if activity else 0

            favorite_button = QPushButton("Saved" if name in favorites else "Save")
            favorite_button.setObjectName("Secondary")
            favorite_button.setMinimumSize(82, 40)
            favorite_button.setMaximumWidth(88)
            favorite_button.setToolTip("Remove from favorites" if name in favorites else "Add to favorites")
            favorite_button.clicked.connect(
                lambda checked=False, boss=name: self._toggle_boss_favorite(boss)
            )
            self.boss_table.setCellWidget(row, 0, favorite_button)

            name_item = QTableWidgetItem(name)
            key = f"boss:{name}"
            path = self._asset_path(key)
            if path:
                name_item.setIcon(QIcon(str(path)))
            elif self.asset_service.can_fetch(key):
                asset_keys.append(key)
            self.boss_table.setItem(row, 1, name_item)
            self.boss_table.setItem(row, 2, QTableWidgetItem(f"{current:,}"))

            if rate and rate.late_mid_rate is not None:
                unit = rate.unit.lower()
                self.boss_table.setItem(
                    row, 3, QTableWidgetItem(f"~{rate.late_mid_rate:g} {unit}/h")
                )
            else:
                self.boss_table.setItem(row, 3, QTableWidgetItem("Special"))

            increment = rate.target_increment(minutes, difficulty) if rate else None
            if increment is None:
                if rate and not rate.targetable:
                    target_text = "Not farmable"
                elif rate and minutes < rate.minimum_session_minutes:
                    target_text = f"Needs {rate.minimum_session_minutes}+ min"
                else:
                    target_text = "No calibrated target"
                self.boss_table.setItem(row, 4, QTableWidgetItem(target_text))
                button = QPushButton("Unavailable")
                button.setEnabled(False)
                button.setMinimumSize(156, 40)
            else:
                target = current + increment
                self.boss_table.setItem(
                    row, 4, QTableWidgetItem(f"+{increment} -> {target:,}")
                )
                button = QPushButton(f"Goal to {target:,}")
                button.setObjectName("Secondary")
                button.setMinimumSize(156, 40)
                button.clicked.connect(
                    lambda checked=False, boss=name: self._generate_boss_goal(boss)
                )

            if rate and rate.note:
                tooltip = rate.note
                for col in range(1, 5):
                    item = self.boss_table.item(row, col)
                    if item:
                        item.setToolTip(tooltip)
                button.setToolTip(tooltip)

            self.boss_table.setCellWidget(row, 5, button)

            details = QPushButton("Details")
            details.setObjectName("Secondary")
            details.setMinimumSize(78, 40)
            details.clicked.connect(
                lambda checked=False, boss=name: self._show_boss_detail(boss)
            )
            self.boss_table.setCellWidget(row, 6, details)

        self._request_assets(asset_keys)

    def _show_boss_detail(self, boss_name: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        rate = boss_rate(boss_name)
        activity = profile.activity(boss_name)
        current = max(0, activity.score) if activity else 0
        favorites = self.store.favorite_bosses(self.state, profile)

        snapshots = self.store.snapshots(self.state, profile)
        observed = []
        for snapshot in snapshots:
            item = snapshot.activity(boss_name)
            if item is not None:
                observed.append(max(0, int(item.score)))
        observed_gain = max(0, observed[-1] - observed[0]) if len(observed) >= 2 else 0

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{boss_name} - Boss Detail")
        dialog.resize(700, 620)
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)

        header = QHBoxLayout()
        icon = QLabel()
        icon.setObjectName("SpriteWell")
        icon.setFixedSize(58, 58)
        path = self._asset_path(f"boss:{boss_name}")
        if path:
            self._set_pixmap(icon, path, 42)
        header.addWidget(icon)
        title_box = QVBoxLayout()
        title = QLabel(boss_name)
        title.setObjectName("Title")
        title_box.addWidget(title)
        subtitle = QLabel(rate.note if rate and rate.note else "Boss/activity data from your public HiScores profile.")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        outer.addLayout(header)

        stats = QFrame()
        stats.setObjectName("TopStatStrip")
        grid = QGridLayout(stats)
        values = [
            ("Current KC", f"{current:,}"),
            ("Observed Gain", f"+{observed_gain:,}"),
            ("Late-mid Pace", f"~{rate.late_mid_rate:g}/h" if rate and rate.late_mid_rate is not None else "Special"),
            ("Next Milestone", f"{self._next_kc_target(current):,}"),
        ]
        for col, (label_text, value_text) in enumerate(values):
            label = QLabel(label_text)
            label.setObjectName("Muted")
            value = QLabel(value_text)
            value.setObjectName("CardTitle")
            grid.addWidget(label, 0, col)
            grid.addWidget(value, 1, col)
        outer.addWidget(stats)

        target_title = QLabel("Session Targets")
        target_title.setObjectName("SectionTitle")
        outer.addWidget(target_title)
        target_table = QTableWidget(4, 4)
        target_table.setHorizontalHeaderLabels(["Session", "Chill", "Moderate", "Grind"])
        target_table.verticalHeader().setVisible(False)
        target_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        target_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        target_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row, minutes in enumerate((15, 30, 60, 120)):
            label = "2+ Hours" if minutes == 120 else ("1 Hour" if minutes == 60 else f"{minutes} Minutes")
            target_table.setItem(row, 0, QTableWidgetItem(label))
            for col, difficulty in enumerate(("chill", "moderate", "grind"), start=1):
                increment = rate.target_increment(minutes, difficulty) if rate else None
                text = f"+{increment} -> {current + increment:,}" if increment is not None else "-"
                target_table.setItem(row, col, QTableWidgetItem(text))
        outer.addWidget(target_table)

        actions = QHBoxLayout()
        favorite = QPushButton("Remove Favorite" if boss_name in favorites else "Add Favorite")
        favorite.setObjectName("Secondary")
        favorite.clicked.connect(lambda: (self._toggle_boss_favorite(boss_name), dialog.accept()))
        actions.addWidget(favorite)
        generate = QPushButton("Generate Boss Goal")
        generate.setObjectName("Primary")
        generate.setEnabled(bool(rate and rate.targetable))
        generate.clicked.connect(lambda: (dialog.accept(), self._generate_boss_goal(boss_name)))
        actions.addWidget(generate)
        actions.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Secondary")
        close.clicked.connect(dialog.reject)
        actions.addWidget(close)
        outer.addLayout(actions)
        dialog.exec()

    def _format_requirement_status(self, item) -> str:
        req = item.requirement
        current = item.current_value
        required = req.required_value
        if req.kind == "total_level":
            return f"Total level {current} / {required}"
        if req.kind == "base_level":
            return f"Lowest skill {current} / {required}"
        if req.kind == "boss_kc":
            return f"{req.target} {current} / {required} KC"
        if req.kind == "skill":
            return f"{req.target} {current} / {required}"
        return req.label or req.target

    def _render_paths(self) -> None:
        profile = self.session.profile
        if not hasattr(self, "paths_cards_layout"):
            return
        self._clear_layout(self.paths_cards_layout)
        if profile is None:
            self.create_path_button.setEnabled(False)
            empty = QLabel("Load an account to evaluate progression paths.")
            empty.setObjectName("Muted")
            self.paths_cards_layout.addWidget(empty)
            self.paths_cards_layout.addStretch(1)
            return

        self.create_path_button.setEnabled(True)
        self._sync_progression_sources(load_diaries=False)
        active_specs = {spec["path_id"]: spec for spec in self.store.active_paths(self.state, profile)}
        active_evaluations = {
            evaluation.path.path_id: evaluation
            for evaluation in self.progression_service.evaluate_active_paths(profile, self._combined_active_specs())
        }
        definitions = self.progression_service.incomplete_definitions(profile)
        if not definitions:
            done = QLabel("Every configured path is complete. Add a custom path when you want a new target.")
            done.setObjectName("Success")
            done.setWordWrap(True)
            self.paths_cards_layout.addWidget(done)
            self.paths_cards_layout.addStretch(1)
            return

        for path in definitions:
            spec = active_specs.get(path.path_id)
            priority = spec.get("priority", "high") if spec else "high"
            evaluation = active_evaluations.get(path.path_id) or self.progression_service.evaluate_path(path, profile, priority)
            blocker = evaluation.current_blocker

            card = QFrame()
            card.setObjectName("PathCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 12, 15, 12)
            card_layout.setSpacing(8)

            top = QHBoxLayout()
            name = QLabel(path.name)
            name.setObjectName("SectionTitle")
            top.addWidget(name)
            if path.is_custom:
                custom = QLabel("CUSTOM")
                custom.setObjectName("GoldPill")
                top.addWidget(custom)
            if spec is not None:
                active = QLabel("ACTIVE")
                active.setObjectName("Pill")
                top.addWidget(active)
            top.addStretch(1)
            percent = QLabel(f"{evaluation.progress_percent:.0f}%")
            percent.setObjectName("CardTitle")
            top.addWidget(percent)
            card_layout.addLayout(top)

            if path.description:
                desc = QLabel(path.description)
                desc.setObjectName("Muted")
                desc.setWordWrap(True)
                card_layout.addWidget(desc)

            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(int(evaluation.progress_percent))
            progress.setTextVisible(False)
            card_layout.addWidget(progress)

            blocker_text = self._format_requirement_status(blocker) if blocker else "No measurable blocker remains"
            blocker_label = QLabel(f"Current blocker: {blocker_text}")
            blocker_label.setWordWrap(True)
            blocker_label.setObjectName("Warning" if blocker else "Success")
            card_layout.addWidget(blocker_label)

            footer = QHBoxLayout()
            footer.setSpacing(8)
            priority_combo = QComboBox()
            priority_combo.addItems(["Low", "Medium", "High", "Critical"])
            priority_combo.setCurrentText(priority.title())
            priority_combo.setEnabled(spec is not None)
            priority_combo.setFixedHeight(34)
            if spec is not None:
                priority_combo.currentTextChanged.connect(
                    lambda text, path_id=path.path_id: self._change_path_priority(path_id, text.lower())
                )
            footer.addWidget(priority_combo)

            generate = QPushButton("Generate Blocker")
            generate.setObjectName("Primary")
            generate.setFixedHeight(36)
            generate.setEnabled(spec is not None and blocker is not None)
            generate.clicked.connect(lambda checked=False, path_id=path.path_id: self._generate_path_goal(path_id))
            footer.addWidget(generate)

            if spec is None:
                toggle = QPushButton("Activate")
                toggle.setObjectName("Primary")
                toggle.clicked.connect(lambda checked=False, path_id=path.path_id: self._activate_path(path_id))
            else:
                toggle = QPushButton("Deactivate")
                toggle.setObjectName("Secondary")
                toggle.clicked.connect(lambda checked=False, path_id=path.path_id: self._deactivate_path(path_id))
            toggle.setFixedHeight(36)
            footer.addWidget(toggle)

            details = QPushButton("Details")
            details.setObjectName("Secondary")
            details.setFixedHeight(36)
            details.clicked.connect(lambda checked=False, path_id=path.path_id: self._show_path_details(path_id))
            footer.addWidget(details)

            if path.is_custom:
                edit = QPushButton("Edit")
                edit.setObjectName("Secondary")
                edit.setFixedHeight(36)
                edit.clicked.connect(lambda checked=False, path_id=path.path_id: self._edit_path_by_id(path_id))
                delete = QPushButton("Delete")
                delete.setObjectName("Danger")
                delete.setFixedHeight(36)
                delete.clicked.connect(lambda checked=False, path_id=path.path_id: self._delete_path_by_id(path_id))
                footer.addWidget(edit)
                footer.addWidget(delete)

            footer.addStretch(1)
            card_layout.addLayout(footer)
            self.paths_cards_layout.addWidget(card)

        self.paths_cards_layout.addStretch(1)

    def _load_diary_definitions(self, *, force_refresh: bool = False) -> bool:
        try:
            self.diary_definitions = self.diary_service.load(force_refresh=force_refresh)
            self.diary_error = None
        except DiaryDataError as exc:
            self.diary_error = str(exc)
            self.diary_definitions = []
            return False

        self.progression_service.set_external_paths([
            self.diary_service.as_path(diary) for diary in self.diary_definitions
        ])

        # Populate the region filter once data exists. Preserve selection when possible.
        current = self.diary_region_combo.currentText() if hasattr(self, "diary_region_combo") else "All Regions"
        if hasattr(self, "diary_region_combo"):
            regions = sorted({diary.name for diary in self.diary_definitions})
            self.diary_region_combo.blockSignals(True)
            self.diary_region_combo.clear()
            self.diary_region_combo.addItem("All Regions")
            self.diary_region_combo.addItems(regions)
            index = self.diary_region_combo.findText(current)
            self.diary_region_combo.setCurrentIndex(index if index >= 0 else 0)
            self.diary_region_combo.blockSignals(False)
        return True

    def _render_diaries(self) -> None:
        if not hasattr(self, "diary_cards_layout"):
            return
        self._clear_layout(self.diary_cards_layout)
        profile = self.session.profile
        if profile is None:
            self.diary_note.setText("Load an account to compare your stats against diary requirements.")
            empty = QLabel("No account loaded.")
            empty.setObjectName("Muted")
            self.diary_cards_layout.addWidget(empty)
            self.diary_cards_layout.addStretch(1)
            return

        if not self.diary_definitions:
            self._load_diary_definitions()
        if self.diary_error:
            self.diary_note.setText(self.diary_error)
            err = QLabel(self.diary_error)
            err.setObjectName("DangerText")
            err.setWordWrap(True)
            self.diary_cards_layout.addWidget(err)
            self.diary_cards_layout.addStretch(1)
            return

        self._sync_progression_sources(load_diaries=False)
        completed = self.store.completed_diaries(self.state, profile)
        tracked = {spec["diary_id"] for spec in self.store.active_diaries(self.state, profile)}
        region_filter = self.diary_region_combo.currentText()
        tier_filter = self.diary_tier_combo.currentText().lower()
        tracked_filter = self.diary_tracked_combo.currentText()

        rows: list[tuple[DiaryDefinition, object, float, bool]] = []
        for diary in self.diary_definitions:
            if diary.diary_id in completed:
                continue
            if region_filter != "All Regions" and diary.name != region_filter:
                continue
            if tier_filter != "all tiers" and diary.tier != tier_filter:
                continue

            path = self.diary_service.as_path(diary)
            evaluation = self.progression_service.evaluate_path(path, profile, "medium")
            measurable = [item for item in evaluation.requirements if item.measurable]
            if measurable:
                total_weight = sum(max(0.1, item.requirement.weight) for item in measurable)
                ready_weight = sum(
                    max(0.1, item.requirement.weight) * (item.progress_percent / 100.0)
                    for item in measurable
                )
                stats_readiness = 100.0 * ready_weight / max(0.1, total_weight)
                stats_ready = all(item.completed for item in measurable)
            else:
                stats_readiness = 100.0
                stats_ready = True

            if tracked_filter == "Tracked Only" and diary.diary_id not in tracked:
                continue
            if tracked_filter == "Stats Ready" and not stats_ready:
                continue
            rows.append((diary, evaluation, stats_readiness, stats_ready))

        self.diary_note.setText(
            "Quest prerequisites are assumed complete. Measurable skill/boss blockers come from the cached diary "
            "requirement dataset; completion stays manual because public HiScores do not expose diary state."
        )

        if not rows:
            empty = QLabel("No incomplete diaries match the current filters.")
            empty.setObjectName("Muted")
            self.diary_cards_layout.addWidget(empty)
            self.diary_cards_layout.addStretch(1)
            return

        for diary, evaluation, readiness, stats_ready in rows:
            blocker = evaluation.current_blocker
            card = QFrame()
            card.setObjectName("DiaryCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 12, 15, 12)
            card_layout.setSpacing(8)

            top = QHBoxLayout()
            name = QLabel(diary.name)
            name.setObjectName("SectionTitle")
            tier = QLabel(diary.tier.upper())
            tier.setObjectName("GoldPill")
            status = QLabel("STATS READY" if stats_ready else f"{readiness:.0f}% READY")
            status.setObjectName("Pill" if stats_ready else "GoldPill")
            top.addWidget(name)
            top.addWidget(tier)
            if diary.diary_id in tracked:
                tracked_badge = QLabel("TRACKED")
                tracked_badge.setObjectName("Pill")
                top.addWidget(tracked_badge)
            top.addStretch(1)
            top.addWidget(status)
            card_layout.addLayout(top)

            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(int(readiness))
            progress.setTextVisible(False)
            card_layout.addWidget(progress)

            blocker_text = self._format_requirement_status(blocker) if blocker else "Measurable stats ready"
            blocker_label = QLabel(f"Current blocker: {blocker_text}")
            blocker_label.setObjectName("Warning" if blocker else "Success")
            blocker_label.setWordWrap(True)
            card_layout.addWidget(blocker_label)
            extra = QLabel(
                f"Remaining manual context: {diary.manual_requirement_count} item/unlock requirement(s) + diary tasks"
                if diary.manual_requirement_count else
                "Remaining manual context: diary tasks"
            )
            extra.setObjectName("Muted")
            extra.setWordWrap(True)
            card_layout.addWidget(extra)

            footer = QHBoxLayout()
            footer.setSpacing(8)
            track = QPushButton("Untrack" if diary.diary_id in tracked else "Track")
            track.setObjectName("Secondary" if diary.diary_id in tracked else "Primary")
            track.setFixedHeight(36)
            track.clicked.connect(lambda checked=False, diary_id=diary.diary_id: self._toggle_diary_tracking(diary_id))
            generate = QPushButton("Generate Blocker")
            generate.setObjectName("Primary")
            generate.setFixedHeight(36)
            generate.setEnabled(blocker is not None)
            generate.clicked.connect(lambda checked=False, diary_id=diary.diary_id: self._generate_diary_goal(diary_id))
            complete = QPushButton("Mark Complete")
            complete.setObjectName("Secondary")
            complete.setFixedHeight(36)
            complete.clicked.connect(lambda checked=False, diary_id=diary.diary_id: self._mark_diary_complete(diary_id))
            footer.addWidget(track)
            footer.addWidget(generate)
            footer.addWidget(complete)
            details = QPushButton("Details")
            details.setObjectName("Secondary")
            details.setFixedHeight(36)
            details.clicked.connect(lambda checked=False, diary_id=diary.diary_id: self._show_diary_detail(diary_id))
            footer.addWidget(details)
            footer.addStretch(1)
            card_layout.addLayout(footer)
            self.diary_cards_layout.addWidget(card)

        self.diary_cards_layout.addStretch(1)

    def _render_collection(self) -> None:
        if not hasattr(self, "collection_cards_layout"):
            return
        self._clear_layout(self.collection_cards_layout)
        profile = self.session.profile
        if profile is None:
            self.collection_overall_value.setText("-")
            self.collection_gain_value.setText("-")
            self.collection_tracked_value.setText("-")
            self.collection_slots_value.setText("-")
            self.collection_runelite_value.setText("-")
            self.collection_add_button.setEnabled(False)
            self.collection_generate_button.setEnabled(False)
            empty = QLabel("Load an account to track Collection Log progress.")
            empty.setObjectName("Muted")
            self.collection_cards_layout.addWidget(empty)
            self.collection_cards_layout.addStretch(1)
            return

        self.collection_add_button.setEnabled(True)
        collection_activity = profile.activity("Collections Logged")
        public_total = (
            int(collection_activity.score)
            if collection_activity is not None and collection_activity.score >= 0
            else None
        )
        self.collection_overall_value.setText(f"{public_total:,}" if public_total is not None else "Not ranked")
        self.collection_generate_button.setEnabled(public_total is not None)

        snapshots = self.store.snapshots(self.state, profile)
        observed_scores = []
        for snapshot in snapshots:
            activity = snapshot.activity("Collections Logged")
            if activity is not None and activity.score >= 0:
                observed_scores.append(int(activity.score))
        gain = max(0, observed_scores[-1] - observed_scores[0]) if len(observed_scores) >= 2 else 0
        self.collection_gain_value.setText(f"+{gain:,}")

        targets = self.store.collection_targets(self.state, profile)
        obtained = sum(int(item["current"]) for item in targets)
        possible = sum(int(item["total"]) for item in targets)
        self.collection_tracked_value.setText(str(len(targets)))
        self.collection_slots_value.setText(f"{obtained:,} / {possible:,}" if possible else "0 / 0")

        bridge_snapshot = self.runelite_snapshot if (self.runelite_snapshot and self.runelite_snapshot.matches(profile)) else None
        bridge_live = bool(bridge_snapshot and bridge_snapshot.is_fresh())
        self.collection_runelite_value.setText(str(bridge_snapshot.collection_page_count) if bridge_snapshot else "0")

        query = self.collection_search.text().strip().casefold()
        status = self.collection_status.currentText()
        active = self.store.active_goal(self.state, profile)
        active_page = active.target_name if active and active.subtype == "collection_slot" else None
        category = self.collection_category.currentText()
        # Categories are local presentation metadata, not account completion data.
        if bridge_snapshot and bridge_snapshot.collection_pages:
            visible_pages = []
            for page_name, page in bridge_snapshot.collection_pages.items():
                if category != "All Categories" and collection_page_category(page_name) != category:
                    continue
                completed = page.total_count > 0 and page.obtained_count == page.total_count
                if query and query not in page_name.casefold():
                    continue
                if status == "Incomplete" and completed:
                    continue
                if status == "Completed" and not completed:
                    continue
                visible_pages.append((page_name, page))
            visible_pages.sort(key=lambda pair: (pair[0] != active_page, pair[0].casefold()))
            synced_title = QLabel(f"RuneLite-synced pages: {len(visible_pages)} shown / {bridge_snapshot.collection_page_count} captured")
            synced_title.setObjectName("SectionTitle")
            self.collection_cards_layout.addWidget(synced_title)
            synced_note = QLabel(
                "These pages came directly from the Collection Log interface in RuneLite. "
                "Open more pages in-game to expand the snapshot; cached pages remain visible when RuneLite is closed. "
                "Search, category, and completion filters apply to synced pages and manual grinds."
            )
            synced_note.setObjectName("Muted")
            synced_note.setWordWrap(True)
            self.collection_cards_layout.addWidget(synced_note)
            if not visible_pages:
                empty_pages = QLabel("No synced pages match. Clear the search, choose All Categories, or set status to All.")
                empty_pages.setObjectName("Muted")
                empty_pages.setWordWrap(True)
                self.collection_cards_layout.addWidget(empty_pages)
            for page_name, page in visible_pages:
                card = QFrame()
                card.setObjectName("CollectionCard")
                card.setProperty("syncedPageName", page_name)
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(15, 12, 15, 12)
                card_layout.setSpacing(7)
                head = QHBoxLayout()
                name_label = QLabel(page_name)
                name_label.setObjectName("SectionTitle")
                badge = QLabel("RUNELITE LIVE" if bridge_live else "RUNELITE CACHED")
                badge.setObjectName("Pill")
                count_label = QLabel(f"{page.obtained_count} / {page.total_count}")
                count_label.setObjectName("CardTitle")
                head.addWidget(name_label)
                category_badge = QLabel(collection_page_category(page_name))
                category_badge.setObjectName("Pill")
                head.addWidget(category_badge)
                head.addWidget(badge)
                if page_name == active_page:
                    active_badge = QLabel("ACTIVE GOAL")
                    active_badge.setObjectName("Pill")
                    head.addWidget(active_badge)
                head.addStretch(1)
                head.addWidget(count_label)
                card_layout.addLayout(head)
                progress = QProgressBar()
                progress.setRange(0, 100)
                pct = int(round((page.obtained_count / page.total_count) * 100)) if page.total_count else 0
                progress.setValue(pct)
                progress.setTextVisible(False)
                card_layout.addWidget(progress)
                missing = [item.name for item in page.missing_items]
                owned = [item.name for item in page.items if item.obtained]
                owned_text = ", ".join(owned[:8]) if owned else "None captured yet"
                missing_text = ", ".join(missing[:8]) if missing else "None"
                if len(owned) > 8:
                    owned_text += f" (+{len(owned) - 8} more)"
                if len(missing) > 8:
                    missing_text += f" (+{len(missing) - 8} more)"
                owned_label = QLabel(f"Obtained: {owned_text}")
                owned_label.setWordWrap(True)
                missing_label = QLabel(f"Missing: {missing_text}")
                missing_label.setWordWrap(True)
                missing_label.setObjectName("Muted")
                card_layout.addWidget(owned_label)
                card_layout.addWidget(missing_label)
                is_active = page_name == active_page
                track = QPushButton("View active goal" if is_active else "Track next unlock")
                track.setObjectName("Primary" if is_active or (bridge_live and page.missing_items and active is None) else "Secondary")
                track.setEnabled(is_active or (bridge_live and bool(page.missing_items) and active is None))
                if is_active:
                    track.clicked.connect(lambda checked=False: self._switch_page(0))
                else:
                    track.clicked.connect(lambda checked=False, name=page_name: self._generate_live_collection_goal(name))
                if not is_active and active:
                    hint = "Finish, cancel, or block your active goal before tracking another."
                elif not page.missing_items:
                    hint = "All captured items on this page are obtained."
                elif not bridge_live:
                    hint = "Connect RuneLite on this account to track an unlock."
                else:
                    hint = "Reopen this page in RuneLite after an unlock to verify progress."
                track.setToolTip(hint)
                action_hint = QLabel(hint)
                action_hint.setObjectName("Muted")
                action_hint.setWordWrap(True)
                card_layout.addWidget(action_hint)
                card_layout.addWidget(track)
                self.collection_cards_layout.addWidget(card)

            separator = QLabel("Manual tracked grinds")
            separator.setObjectName("SectionTitle")
            self.collection_cards_layout.addWidget(separator)

        query = self.collection_search.text().strip().casefold()
        category = self.collection_category.currentText()
        status = self.collection_status.currentText()
        visible = []
        for target in targets:
            completed = int(target["current"]) >= int(target["total"])
            if query and query not in str(target["name"]).casefold() and query not in str(target.get("notes", "")).casefold():
                continue
            if category != "All Categories" and target.get("category") != category:
                continue
            if status == "Incomplete" and completed:
                continue
            if status == "Completed" and not completed:
                continue
            visible.append(target)

        if not visible:
            message = (
                "No manual tracked grinds match the current filters."
                if targets else
                "No manual grinds are tracked. RuneLite-synced pages above are automatic; use + Track Grind only for anything you still want to maintain manually."
            )
            empty = QLabel(message)
            empty.setObjectName("Muted")
            empty.setWordWrap(True)
            self.collection_cards_layout.addWidget(empty)
            self.collection_cards_layout.addStretch(1)
            return

        for target in sorted(visible, key=lambda item: (str(item.get("category", "")), str(item["name"]).casefold())):
            current = int(target["current"])
            total = max(1, int(target["total"]))
            completed = current >= total
            percent = min(100, int(round((current / total) * 100)))

            card = QFrame()
            card.setObjectName("CollectionCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 12, 15, 12)
            card_layout.setSpacing(8)

            top = QHBoxLayout()
            name = QLabel(str(target["name"]))
            name.setObjectName("SectionTitle")
            top.addWidget(name)
            category_badge = QLabel(str(target.get("category", "Other")).upper())
            category_badge.setObjectName("GoldPill")
            top.addWidget(category_badge)
            if completed:
                badge = QLabel("COMPLETE")
                badge.setObjectName("Pill")
                top.addWidget(badge)
            top.addStretch(1)
            count = QLabel(f"{current} / {total}")
            count.setObjectName("CardTitle")
            top.addWidget(count)
            card_layout.addLayout(top)

            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(percent)
            progress.setTextVisible(False)
            card_layout.addWidget(progress)

            notes = str(target.get("notes", "")).strip()
            if notes:
                note = QLabel(notes)
                note.setObjectName("Muted")
                note.setWordWrap(True)
                card_layout.addWidget(note)

            footer = QHBoxLayout()
            footer.setSpacing(8)
            add_slot = QPushButton("+1 Slot")
            add_slot.setObjectName("Primary")
            add_slot.setFixedHeight(36)
            add_slot.setEnabled(not completed)
            add_slot.clicked.connect(
                lambda checked=False, target_id=target["target_id"]: self._increment_collection_target(target_id)
            )
            footer.addWidget(add_slot)
            goal = QPushButton("Set Goal")
            goal.setObjectName("Secondary")
            goal.setFixedHeight(36)
            goal.setEnabled(not completed)
            goal.clicked.connect(
                lambda checked=False, target_id=target["target_id"]: self._generate_collection_target_goal(target_id)
            )
            footer.addWidget(goal)
            edit = QPushButton("Edit")
            edit.setObjectName("Secondary")
            edit.setFixedHeight(36)
            edit.clicked.connect(
                lambda checked=False, target_id=target["target_id"]: self._edit_collection_target(target_id)
            )
            footer.addWidget(edit)
            delete = QPushButton("Delete")
            delete.setObjectName("Danger")
            delete.setFixedHeight(36)
            delete.clicked.connect(
                lambda checked=False, target_id=target["target_id"]: self._delete_collection_target(target_id)
            )
            footer.addWidget(delete)
            footer.addStretch(1)
            card_layout.addLayout(footer)
            self.collection_cards_layout.addWidget(card)

        self.collection_cards_layout.addStretch(1)

    def _render_stats(self) -> None:
        profile = self.session.profile
        self.stats_skill_table.setRowCount(0)
        self.stats_activity_table.setRowCount(0)

        if profile is None:
            self.stats_tracking.setText("Snapshots\n-")
            self.stats_xp.setText("XP Gained\n-")
            self.stats_levels.setText("Levels Gained\n-")
            self.stats_completion.setText("Task Completion\n-")
            self.stats_goal_summary.setText("Load an account to build analytics.")
            return

        summary = self.analytics_service.summarize(
            self.store.snapshots(self.state, profile),
            self.store.goal_history(self.state, profile),
            self.store.active_goal(self.state, profile),
        )

        day_text = f"  |  {summary.tracking_days} day{'s' if summary.tracking_days != 1 else ''}" if summary.snapshot_count > 1 else ""
        self.stats_tracking.setText(f"Snapshots\n{summary.snapshot_count}{day_text}")
        self.stats_xp.setText(f"XP Gained\n+{summary.total_xp_gained:,}")
        self.stats_levels.setText(f"Levels Gained\n+{summary.total_levels_gained}")
        completion = f"{summary.completion_rate:.0f}%" if (summary.completed_tasks + summary.cancelled_tasks + summary.blocked_tasks) else "-"
        self.stats_completion.setText(f"Task Completion\n{completion}")

        top_skills = summary.skill_gains[:12]
        self.stats_skill_table.setRowCount(len(top_skills))
        for row, gain in enumerate(top_skills):
            self.stats_skill_table.setItem(row, 0, QTableWidgetItem(gain.name))
            self.stats_skill_table.setItem(row, 1, QTableWidgetItem(f"+{gain.xp_delta:,}"))
            level_text = f"+{gain.level_delta}" if gain.level_delta else "-"
            self.stats_skill_table.setItem(row, 2, QTableWidgetItem(level_text))

        top_activities = summary.activity_gains[:12]
        self.stats_activity_table.setRowCount(len(top_activities))
        for row, gain in enumerate(top_activities):
            self.stats_activity_table.setItem(row, 0, QTableWidgetItem(gain.name))
            self.stats_activity_table.setItem(row, 1, QTableWidgetItem(f"+{gain.delta:,}"))

        favorite = summary.favorite_category.title() if summary.favorite_category else "-"
        strongest = summary.strongest_category.title() if summary.strongest_category else "-"
        categories = sorted(
            summary.category_counts.items(), key=lambda item: item[1], reverse=True
        )
        category_text = ", ".join(f"{name.title()} {count}" for name, count in categories[:5]) or "None yet"
        self.stats_goal_summary.setText(
            f"Accepted: {summary.accepted_tasks}   |   Completed: {summary.completed_tasks}   |   "
            f"Cancelled: {summary.cancelled_tasks}   |   Blocked: {summary.blocked_tasks}\n"
            f"Most chosen category: {favorite}   |   Most completed category: {strongest}\n"
            f"Category mix: {category_text}"
        )

    def _render_history(self) -> None:
        profile = self.session.profile
        self.history_table.setRowCount(0)
        if profile is None:
            return
        history = list(reversed(self.store.goal_history(self.state, profile)))
        self.history_table.setRowCount(len(history))
        for row, goal in enumerate(history):
            accepted = goal.accepted_at or goal.generated_at
            self.history_table.setItem(row, 0, QTableWidgetItem(accepted))
            self.history_table.setItem(row, 1, QTableWidgetItem(goal.title))
            self.history_table.setItem(row, 2, QTableWidgetItem(goal.category.title()))
            self.history_table.setItem(row, 3, QTableWidgetItem(goal.status.title()))
            self.history_table.setItem(row, 4, QTableWidgetItem(f"{goal.progress_percent:.0f}%"))
            self.history_table.setItem(row, 5, QTableWidgetItem(f"{goal.score:.0f}"))

    def _render_settings(self) -> None:
        self.blocked_list.clear()
        self.completed_diary_list.clear()
        profile = self.session.profile
        snapshot = self.runelite_snapshot
        if hasattr(self, "runelite_bridge_status"):
            active = self.store.active_goal(self.state, profile) if profile else None
            status = bridge_status(snapshot, profile, active,
                                   file_exists=self.runelite_sync_service.path.exists())
            self.runelite_bridge_status.setText(status.title)
            self.runelite_bridge_status.setObjectName("Pill" if status.live else "GoldPill")
            detail = status.detail
            if snapshot:
                detail += (f"\nAccount: {snapshot.player_name or '-'} | "
                           f"Cached pages: {snapshot.collection_page_count} | "
                           f"Last bridge update: {snapshot.updated_at}")
            self.runelite_bridge_detail.setWordWrap(True)
            self.runelite_bridge_detail.setText(detail)
            self.runelite_bridge_status.style().unpolish(self.runelite_bridge_status)
            self.runelite_bridge_status.style().polish(self.runelite_bridge_status)
        if profile is None:
            self.blocked_list.addItem("Load an account to manage account-specific blocks.")
            self.completed_diary_list.addItem("Load an account to manage diary completion.")
            self.reroll_memory_label.setText("Reroll memory: load an account")
            return

        prefs = self.store.preferences(self.state, profile)
        rerolls = list(prefs.get("rerolled_targets", []))
        if rerolls:
            self.reroll_memory_label.setText(
                f"Reroll memory: {len(rerolls)} target(s) - " + ", ".join(rerolls[:4]) + ("..." if len(rerolls) > 4 else "")
            )
        else:
            self.reroll_memory_label.setText("Reroll memory: empty")
        blocked = prefs.get("blocked_targets", [])
        if not blocked:
            self.blocked_list.addItem("No blocked targets.")
        else:
            for target in blocked:
                self.blocked_list.addItem(target)

        completed = sorted(self.store.completed_diaries(self.state, profile))
        if not completed:
            self.completed_diary_list.addItem("No manually completed diaries.")
        else:
            lookup = {diary.diary_id: diary for diary in self.diary_definitions}
            for diary_id in completed:
                diary = lookup.get(diary_id)
                label = (
                    f"{diary.name} {diary.tier.title()}"
                    if diary else diary_id.replace("_", " ").replace(":", " - ").title()
                )
                # QListWidget accepts addItem(str); store the diary id on the created item.
                # store the id in a parallel property via the item's UserRole.
                self.completed_diary_list.addItem(label)
                list_item = self.completed_diary_list.item(self.completed_diary_list.count() - 1)
                list_item.setData(Qt.ItemDataRole.UserRole, diary_id)

    # ------------------------------------------------------------------
    # Goal generation / feedback
    # ------------------------------------------------------------------

    def _context(self, minutes: int) -> ScoringContext:
        profile = self.session.profile
        if profile is None:
            return ScoringContext(session_minutes=minutes)
        prefs = self.store.preferences(self.state, profile)
        weights = prefs.get("category_weights", {})
        preferred = {name for name, value in weights.items() if value > 0}
        disliked = {name for name, value in weights.items() if value < 0}
        self._sync_progression_sources(load_diaries=False)
        path_data = self.progression_service.scoring_data(
            profile,
            self._combined_active_specs(),
        )
        return ScoringContext(
            session_minutes=minutes,
            active_path_targets=path_data.active_path_targets,
            blocker_targets=path_data.blocker_targets,
            path_target_counts=path_data.path_target_counts,
            path_priority_bonus=path_data.path_priority_bonus,
            preferred_categories=preferred,
            disliked_categories=disliked,
            recent_targets=list(prefs.get("recent_targets", [])),
            blocked_targets=set(prefs.get("blocked_targets", [])),
            rerolled_targets=list(prefs.get("rerolled_targets", [])),
        )

    def _generate_goal(self) -> None:
        profile = self.session.profile
        if profile is None:
            QMessageBox.information(self, APP_NAME, "Load an account first.")
            return
        if self.store.active_goal(self.state, profile) is not None:
            QMessageBox.information(
                self,
                APP_NAME,
                "You already have an active task. Complete, cancel, or block it before generating another.",
            )
            return

        category = self.category_combo.currentText().lower()
        difficulty = self.difficulty_combo.currentText().lower()
        minutes = int(self.session_combo.currentData())
        filters = GoalFilters(category=category, difficulty=difficulty, session_minutes=minutes)
        try:
            goal = self.goal_engine.choose_goal(profile, filters, self._context(minutes))
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.session.current_goal = goal
        self._render_generated_goal(goal)

    def _generate_boss_goal(self, boss_name: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        if self.store.active_goal(self.state, profile) is not None:
            QMessageBox.information(
                self,
                APP_NAME,
                "You already have an active task. Complete, cancel, or block it before generating a boss task.",
            )
            self._switch_page(0)
            return

        difficulty = self.boss_difficulty_combo.currentText().lower()
        minutes = int(self.boss_session_combo.currentData())
        filters = GoalFilters(category="bossing", difficulty=difficulty, session_minutes=minutes)
        try:
            goal = self.goal_engine.choose_boss_goal(
                profile,
                boss_name,
                filters,
                self._context(minutes),
            )
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.session.current_goal = goal
        self._render_generated_goal(goal)
        self._switch_page(0)

    def _render_generated_goal(self, goal: Goal) -> None:
        self.session.current_goal = goal
        self._render_goal_panel()

    def _reroll_goal(self) -> None:
        profile = self.session.profile
        if profile is None:
            return
        if self.store.active_goal(self.state, profile) is not None:
            return
        goal = self.session.current_goal
        if goal:
            self.store.record_reroll(self.state, profile, goal.target_name)
            self.store.save(self.state)
        self._generate_goal()

    def _clear_reroll_memory(self) -> None:
        profile = self.session.profile
        if profile is None:
            QMessageBox.information(self, APP_NAME, "Load an account first.")
            return

        prefs = self.store.preferences(self.state, profile)
        rerolls = list(prefs.get("rerolled_targets", []))
        if not rerolls:
            QMessageBox.information(self, APP_NAME, "Reroll memory is already empty.")
            return

        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Clear {len(rerolls)} remembered reroll target(s)?\n\n"
            "This does not change blocked targets, history, or your active task.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.store.clear_rerolls(self.state, profile)
        self.store.save(self.state)
        self._render_home()
        self._render_settings()
        QMessageBox.information(self, APP_NAME, "Reroll memory cleared. The recommendation pool is fresh again.")

    def _block_current_target(self) -> None:
        profile = self.session.profile
        if profile is None:
            QMessageBox.information(self, APP_NAME, "Load an account first.")
            return

        active = self.store.active_goal(self.state, profile)
        goal = active or self.session.current_goal
        if goal is None:
            QMessageBox.information(self, APP_NAME, "Generate a task first.")
            return

        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Block {goal.target_name} from future recommendations for this account?\n\n"
            "You can unblock it later in Settings.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.store.block_target(self.state, profile, goal.target_name)
        if active is not None:
            self.store.archive_active_goal(self.state, profile, "blocked")
        self.session.current_goal = None
        self.store.save(self.state)
        self._render_all()

    def _accept_goal(self) -> None:
        profile = self.session.profile
        goal = self.session.current_goal
        if profile is None or goal is None:
            QMessageBox.information(self, APP_NAME, "Generate a task first.")
            return

        if self.store.active_goal(self.state, profile) is not None:
            QMessageBox.information(
                self,
                APP_NAME,
                "A task is already active. Complete, cancel, or block it first.",
            )
            return

        if goal.subtype == "collection_slot":
            try:
                # Re-read and rebaseline at acceptance, not when the preview opened.
                goal = self.progress_service.collection_goal(profile, self._refresh_runelite_snapshot(), goal.target_name)
                self.session.current_goal = goal
            except ValueError as exc:
                QMessageBox.information(self, APP_NAME, str(exc))
                return
        goal.status = "accepted"
        goal.accepted_at = datetime.now().isoformat(timespec="seconds")
        self.progress_service.apply(goal, profile, self.runelite_snapshot)
        self.store.set_active_goal(self.state, profile, goal)
        self.session.current_goal = None
        self.store.record_recent_target(self.state, profile, goal.target_name)
        self.store.clear_rerolls(self.state, profile)
        self.store.save(self.state)
        self._render_all()
        QMessageBox.information(self, APP_NAME, "Task locked in and now actively tracked.")

    def _mark_active_complete(self) -> None:
        profile = self.session.profile
        if profile is None:
            return
        active = self.store.active_goal(self.state, profile)
        if active is None:
            QMessageBox.information(self, APP_NAME, "There is no active task to complete.")
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Mark this task complete manually?\n\n{active.title}",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        active.status = "completed"
        active.completed_at = datetime.now().isoformat(timespec="seconds")
        active.progress_percent = 100.0
        collection_target_id = active.metadata.get("collection_target_id")
        if collection_target_id:
            target = self._collection_target_by_id(str(collection_target_id))
            if target is not None and int(target["current"]) < int(target["total"]):
                target["current"] = int(target["current"]) + 1
                self.store.save_collection_target(self.state, profile, target)
        self.store.update_active_goal(self.state, profile, active)
        self.store.archive_active_goal(self.state, profile, "completed")
        self.session.current_goal = None
        self.store.save(self.state)
        self._render_all()

    def _cancel_active_goal(self) -> None:
        profile = self.session.profile
        if profile is None:
            return
        active = self.store.active_goal(self.state, profile)
        if active is None:
            QMessageBox.information(self, APP_NAME, "There is no active task to cancel.")
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Cancel this task?\n\n{active.title}\n\nIt will remain in History as Cancelled.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.archive_active_goal(self.state, profile, "cancelled")
        self.session.current_goal = None
        self.store.save(self.state)
        self._render_all()

    # Backward-compatible internal alias for Alpha 2 references.
    def _abandon_active_goal(self) -> None:
        self._cancel_active_goal()

    def _toggle_boss_favorite(self, boss_name: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        self.store.toggle_favorite_boss(self.state, profile, boss_name)
        self.store.save(self.state)
        self._render_bosses()

    def _show_path_details(self, path_id: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        path = self.progression_service.definition(path_id)
        if path is None:
            return
        evaluation = self.progression_service.evaluate_path(path, profile, "medium")
        lines: list[str] = []
        for req_eval in evaluation.requirements:
            marker = "[x]" if req_eval.completed else ("[ ]" if req_eval.measurable else "[-]")
            detail = (
                self._format_requirement_status(req_eval)
                if req_eval.measurable
                else (req_eval.requirement.label or req_eval.requirement.target)
            )
            lines.append(f"{marker} {detail}")
        QMessageBox.information(
            self,
            path.name,
            f"{path.description or 'Progression path'}\n\n" + "\n".join(lines),
        )

    def _edit_path_by_id(self, path_id: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        path = self.progression_service.definition(path_id)
        if path is None or not path.is_custom:
            return
        dialog = CustomPathDialog(profile, path=path, parent=self)
        if not dialog.exec():
            return
        updated = dialog.path_definition()
        self.store.save_custom_path(self.state, profile, updated)
        self.store.save(self.state)
        self._sync_progression_sources(load_diaries=False)
        self._prune_completed_active_paths()
        self._render_paths()
        self._render_home()

    def _delete_path_by_id(self, path_id: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        path = self.progression_service.definition(path_id)
        if path is None or not path.is_custom:
            return
        answer = QMessageBox.question(self, APP_NAME, f"Delete custom path '{path.name}'?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete_custom_path(self.state, profile, path_id)
        self.store.save(self.state)
        self._sync_progression_sources(load_diaries=False)
        self._render_paths()
        self._render_home()

    def _create_custom_path(self) -> None:
        profile = self.session.profile
        if profile is None:
            QMessageBox.information(self, APP_NAME, "Load an account first.")
            return
        dialog = CustomPathDialog(profile, parent=self)
        if not dialog.exec():
            return
        path = dialog.path_definition()
        self.store.save_custom_path(self.state, profile, path)
        self.store.save(self.state)
        self._sync_progression_sources(load_diaries=False)
        self._render_paths()

    def _refresh_diary_requirements(self) -> None:
        profile = self.session.profile
        if profile is None:
            QMessageBox.information(self, APP_NAME, "Load an account first.")
            return
        self.diary_refresh_button.setEnabled(False)
        self.diary_refresh_button.setText("Refreshing...")
        ok = self._load_diary_definitions(force_refresh=True)
        self.diary_refresh_button.setEnabled(True)
        self.diary_refresh_button.setText("Refresh Requirements")
        self._sync_progression_sources(load_diaries=False)
        self._render_diaries()
        if ok:
            QMessageBox.information(self, APP_NAME, "Diary requirement data refreshed.")
        else:
            QMessageBox.warning(self, APP_NAME, self.diary_error or "Diary refresh failed.")

    def _find_diary(self, diary_id: str) -> DiaryDefinition | None:
        if not self.diary_definitions:
            self._load_diary_definitions()
        return next((d for d in self.diary_definitions if d.diary_id == diary_id), None)

    def _toggle_diary_tracking(self, diary_id: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        tracked = {spec["diary_id"] for spec in self.store.active_diaries(self.state, profile)}
        if diary_id in tracked:
            self.store.untrack_diary(self.state, profile, diary_id)
        else:
            self.store.track_diary(self.state, profile, diary_id, "medium")
        self.store.save(self.state)
        self._sync_progression_sources(load_diaries=True)
        self._render_diaries()
        self._render_home()

    def _generate_diary_goal(self, diary_id: str) -> None:
        profile = self.session.profile
        if profile is None:
            QMessageBox.information(self, APP_NAME, "Load an account first.")
            return
        if self.store.active_goal(self.state, profile) is not None:
            QMessageBox.information(
                self,
                APP_NAME,
                "You already have an active task. Complete, cancel, or block it before generating a diary task.",
            )
            self._switch_page(0)
            return

        diary = self._find_diary(diary_id)
        if diary is None:
            QMessageBox.warning(self, APP_NAME, "Diary requirement data is unavailable.")
            return
        path = self.diary_service.as_path(diary)
        self.progression_service.set_external_paths([
            self.diary_service.as_path(item) for item in self.diary_definitions
        ])
        active_evaluations = {
            item.path.path_id: item
            for item in self.progression_service.evaluate_active_paths(
                profile, self._combined_active_specs()
            )
        }
        evaluation = active_evaluations.get(path.path_id) or self.progression_service.evaluate_path(
            path, profile, "medium"
        )
        difficulty = self.difficulty_combo.currentText().lower()
        minutes = int(self.session_combo.currentData())
        filters = GoalFilters(category="progression", difficulty=difficulty, session_minutes=minutes)
        try:
            goal = self.goal_engine.choose_path_goal(
                profile, evaluation, filters, self._context(minutes)
            )
        except ValueError as exc:
            QMessageBox.information(
                self,
                APP_NAME,
                f"{exc}\n\nYour measurable diary requirements may already be ready; finish the remaining tasks in-game.",
            )
            return
        self.session.current_goal = goal
        self._render_generated_goal(goal)
        self._switch_page(0)

    def _show_diary_detail(self, diary_id: str) -> None:
        profile = self.session.profile
        diary = self._find_diary(diary_id)
        if profile is None or diary is None:
            return
        path = self.diary_service.as_path(diary)
        evaluation = self.progression_service.evaluate_path(path, profile, "medium")
        measurable = [item for item in evaluation.requirements if item.measurable]
        ready = all(item.completed for item in measurable) if measurable else True
        tracked = diary_id in {spec["diary_id"] for spec in self.store.active_diaries(self.state, profile)}

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{diary.name} {diary.tier.title()} Diary")
        dialog.resize(760, 640)
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(12)

        title_row = QHBoxLayout()
        title = QLabel(f"{diary.name} {diary.tier.title()}")
        title.setObjectName("Title")
        title_row.addWidget(title)
        tier = QLabel(diary.tier.upper())
        tier.setObjectName("GoldPill")
        title_row.addWidget(tier)
        if tracked:
            tracked_badge = QLabel("TRACKED")
            tracked_badge.setObjectName("Pill")
            title_row.addWidget(tracked_badge)
        title_row.addStretch(1)
        outer.addLayout(title_row)

        note = QLabel(
            "Quest prerequisites are assumed complete. Skill/boss rows are verified from public HiScores; "
            "items, unlock alternatives, and the diary tasks themselves remain manual."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        outer.addWidget(note)

        status = QFrame()
        status.setObjectName("TopStatStrip")
        status_grid = QGridLayout(status)
        completed_measurable = sum(1 for item in measurable if item.completed)
        summary = [
            ("Measurable Ready", f"{completed_measurable} / {len(measurable)}"),
            ("Stats Status", "READY" if ready else "BLOCKED"),
            ("Manual Context", str(diary.manual_requirement_count)),
        ]
        for col, (label_text, value_text) in enumerate(summary):
            status_grid.addWidget(QLabel(label_text), 0, col)
            value = QLabel(value_text)
            value.setObjectName("CardTitle")
            status_grid.addWidget(value, 1, col)
        outer.addWidget(status)

        table = QTableWidget(len(evaluation.requirements), 4)
        table.setHorizontalHeaderLabels(["Requirement", "Current", "Status", "Source"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        for row, item in enumerate(evaluation.requirements):
            req = item.requirement
            table.setItem(row, 0, QTableWidgetItem(req.label or req.target))
            current = "Manual" if not item.measurable else str(item.current_value)
            table.setItem(row, 1, QTableWidgetItem(current))
            table.setItem(row, 2, QTableWidgetItem("Ready" if item.completed else ("Manual" if not item.measurable else "Needed")))
            source = "HiScores" if item.measurable else "Manual"
            table.setItem(row, 3, QTableWidgetItem(source))
        outer.addWidget(table, 1)

        actions = QHBoxLayout()
        track = QPushButton("Untrack" if tracked else "Track")
        track.setObjectName("Secondary" if tracked else "Primary")
        track.clicked.connect(lambda: (dialog.accept(), self._toggle_diary_tracking(diary_id)))
        actions.addWidget(track)
        generate = QPushButton("Generate Blocker")
        generate.setObjectName("Primary")
        generate.setEnabled(evaluation.current_blocker is not None)
        generate.clicked.connect(lambda: (dialog.accept(), self._generate_diary_goal(diary_id)))
        actions.addWidget(generate)
        complete = QPushButton("Mark Complete")
        complete.setObjectName("Secondary")
        complete.clicked.connect(lambda: (dialog.accept(), self._mark_diary_complete(diary_id)))
        actions.addWidget(complete)
        actions.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Secondary")
        close.clicked.connect(dialog.reject)
        actions.addWidget(close)
        outer.addLayout(actions)
        dialog.exec()

    def _mark_diary_complete(self, diary_id: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        diary = self._find_diary(diary_id)
        label = f"{diary.name} {diary.tier.title()}" if diary else diary_id
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Mark {label} as complete?\n\nIt will disappear from the Diaries page. You can restore it in Settings.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.mark_diary_complete(self.state, profile, diary_id)
        self.store.save(self.state)
        self._sync_progression_sources(load_diaries=True)
        self._render_diaries()
        self._render_home()
        self._render_settings()

    def _restore_selected_diary(self) -> None:
        profile = self.session.profile
        item = self.completed_diary_list.currentItem()
        if profile is None or item is None:
            return
        diary_id = item.data(Qt.ItemDataRole.UserRole)
        if not diary_id:
            return
        self.store.restore_diary(self.state, profile, str(diary_id))
        self.store.save(self.state)
        self._render_settings()
        if self.diary_definitions:
            self._render_diaries()

    def _collection_target_by_id(self, target_id: str) -> dict | None:
        profile = self.session.profile
        if profile is None:
            return None
        return next(
            (item for item in self.store.collection_targets(self.state, profile) if item["target_id"] == target_id),
            None,
        )

    def _add_collection_target(self) -> None:
        profile = self.session.profile
        if profile is None:
            QMessageBox.information(self, APP_NAME, "Load an account first.")
            return
        dialog = CollectionTargetDialog(parent=self)
        if not dialog.exec():
            return
        self.store.save_collection_target(self.state, profile, dialog.target())
        self.store.save(self.state)
        self._render_collection()

    def _edit_collection_target(self, target_id: str) -> None:
        profile = self.session.profile
        target = self._collection_target_by_id(target_id)
        if profile is None or target is None:
            return
        dialog = CollectionTargetDialog(target=target, parent=self)
        if not dialog.exec():
            return
        self.store.save_collection_target(self.state, profile, dialog.target())
        self.store.save(self.state)
        self._render_collection()

    def _increment_collection_target(self, target_id: str) -> None:
        profile = self.session.profile
        target = self._collection_target_by_id(target_id)
        if profile is None or target is None:
            return
        if int(target["current"]) < int(target["total"]):
            target["current"] = int(target["current"]) + 1
            self.store.save_collection_target(self.state, profile, target)
            self.store.save(self.state)
        self._render_collection()

    def _delete_collection_target(self, target_id: str) -> None:
        profile = self.session.profile
        target = self._collection_target_by_id(target_id)
        if profile is None or target is None:
            return
        answer = QMessageBox.question(self, APP_NAME, f"Delete tracked collection grind '{target['name']}'?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete_collection_target(self.state, profile, target_id)
        self.store.save(self.state)
        self._render_collection()

    def _generate_collection_goal(self) -> None:
        profile = self.session.profile
        if profile is None:
            QMessageBox.information(self, APP_NAME, "Load an account first.")
            return
        if self.store.active_goal(self.state, profile) is not None:
            QMessageBox.information(self, APP_NAME, "Finish, cancel, or block your active task first.")
            self._switch_page(0)
            return
        filters = GoalFilters(
            category="collection",
            difficulty=self.difficulty_combo.currentText().lower(),
            session_minutes=int(self.session_combo.currentData()),
        )
        try:
            goal = self.goal_engine.choose_goal(profile, filters, self._context(filters.session_minutes))
        except ValueError as exc:
            QMessageBox.information(self, APP_NAME, str(exc))
            return
        self.session.current_goal = goal
        self._render_generated_goal(goal)
        self._switch_page(0)

    def _generate_live_collection_goal(self, page_name: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        if self.store.active_goal(self.state, profile) is not None:
            QMessageBox.information(self, APP_NAME, "Finish, cancel, or block your active task first.")
            return
        try:
            goal = self.progress_service.collection_goal(profile, self._refresh_runelite_snapshot(), page_name)
        except ValueError as exc:
            QMessageBox.information(self, APP_NAME, str(exc))
            return
        self.session.current_goal = goal
        self._render_generated_goal(goal)
        self._switch_page(0)

    def _generate_collection_target_goal(self, target_id: str) -> None:
        profile = self.session.profile
        target = self._collection_target_by_id(target_id)
        if profile is None or target is None:
            return
        if self.store.active_goal(self.state, profile) is not None:
            QMessageBox.information(self, APP_NAME, "Finish, cancel, or block your active task first.")
            self._switch_page(0)
            return
        current = int(target["current"])
        total = int(target["total"])
        if current >= total:
            QMessageBox.information(self, APP_NAME, "That tracked collection grind is already complete.")
            return
        goal = Goal(
            goal_id=uuid.uuid4().hex[:12],
            generated_at=datetime.now().isoformat(timespec="seconds"),
            category="collection",
            subtype="manual_collection_target",
            target_name=str(target["name"]),
            title=f"Collection Hunt: {target['name']}",
            objective=f"Obtain one new slot toward {target['name']} ({current} / {total}).",
            reasons=[
                "You explicitly chose this tracked Collection Log grind.",
                "Specific source slots are not exposed by public HiScores, so completion is confirmed manually.",
            ],
            start_value=None,
            target_value=None,
            estimated_minutes=int(self.session_combo.currentData()),
            metadata={
                "collection_target_id": target_id,
                "collection_start": current,
                "collection_total": total,
                "difficulty": self.difficulty_combo.currentText().lower(),
                "session_minutes": int(self.session_combo.currentData()),
            },
        )
        self.session.current_goal = goal
        self._render_generated_goal(goal)
        self._switch_page(0)

    def _generate_path_goal(self, path_id: str) -> None:
        profile = self.session.profile
        if profile is None:
            QMessageBox.information(self, APP_NAME, "Load an account first.")
            return
        if self.store.active_goal(self.state, profile) is not None:
            QMessageBox.information(
                self,
                APP_NAME,
                "You already have an active task. Complete, cancel, or block it before generating a path task.",
            )
            self._switch_page(0)
            return

        active_specs = {
            spec["path_id"]: spec
            for spec in self.store.active_paths(self.state, profile)
        }
        spec = active_specs.get(path_id)
        path = self.progression_service.definition(path_id)
        if spec is None or path is None:
            QMessageBox.information(self, APP_NAME, "Activate this path first.")
            return

        evaluations = {
            item.path.path_id: item
            for item in self.progression_service.evaluate_active_paths(
                profile, self._combined_active_specs()
            )
        }
        evaluation = evaluations.get(path_id) or self.progression_service.evaluate_path(
            path, profile, spec.get("priority", "high")
        )
        difficulty = self.difficulty_combo.currentText().lower()
        minutes = int(self.session_combo.currentData())
        filters = GoalFilters(category="progression", difficulty=difficulty, session_minutes=minutes)
        try:
            goal = self.goal_engine.choose_path_goal(
                profile, evaluation, filters, self._context(minutes)
            )
        except ValueError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return

        self.session.current_goal = goal
        self._render_generated_goal(goal)
        self._switch_page(0)

    def _activate_path(self, path_id: str) -> None:
        profile = self.session.profile
        if profile is None:
            QMessageBox.information(self, APP_NAME, "Load an account first.")
            return
        self.store.activate_path(self.state, profile, path_id, "high")
        self.store.save(self.state)
        self._render_paths()
        self._render_home()

    def _deactivate_path(self, path_id: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        self.store.deactivate_path(self.state, profile, path_id)
        self.store.save(self.state)
        self._render_paths()
        self._render_home()

    def _change_path_priority(self, path_id: str, priority: str) -> None:
        profile = self.session.profile
        if profile is None:
            return
        active_ids = {
            spec["path_id"]
            for spec in self.store.active_paths(self.state, profile)
        }
        if path_id not in active_ids:
            return
        self.store.update_path_priority(self.state, profile, path_id, priority)
        self.store.save(self.state)
        self._render_home()

    def _unblock_selected(self) -> None:
        profile = self.session.profile
        if profile is None:
            return
        item = self.blocked_list.currentItem()
        if item is None:
            return
        target = item.text()
        prefs = self.store.preferences(self.state, profile)
        blocked = prefs.get("blocked_targets", [])
        if target in blocked:
            blocked.remove(target)
            self.store.save(self.state)
            self._render_settings()

    # ------------------------------------------------------------------
    # Wiki assets
    # ------------------------------------------------------------------

    def _goal_asset_key(self, goal: Goal | None) -> str | None:
        if goal is None:
            return None
        profile = self.session.profile
        if profile and goal.target_name in profile.skills:
            return f"skill:{goal.target_name}"
        if boss_rate(goal.target_name) is not None:
            return f"boss:{goal.target_name}"
        if goal.category == "collection":
            return "goal:collection"
        if goal.category == "money":
            return "goal:money"
        if goal.category == "clues":
            return "goal:clues"
        return None

    def _render_goal_icon(self, goal: Goal | None) -> None:
        if not hasattr(self, "goal_icon"):
            return
        self.goal_icon.clear()
        key = self._goal_asset_key(goal)
        if key:
            path = self._asset_path(key)
            if path:
                self._set_pixmap(self.goal_icon, path, 68)
                self.goal_icon.setText("")
                return
            if self.asset_service.can_fetch(key):
                self._request_assets([key])
        if goal is None:
            fallback = "GOAL"
        else:
            fallback = {
                "bossing": "BOSS",
                "collection": "LOG",
                "money": "GP",
                "clues": "CLUE",
            }.get(goal.category, "SKILL")
        self.goal_icon.setText(fallback)

    def _asset_path(self, key: str) -> Path | None:
        if key in self.cached_assets and self.cached_assets[key].exists():
            return self.cached_assets[key]
        cached = self.asset_service.cached_path(key)
        if cached:
            self.cached_assets[key] = cached
            return cached
        return None

    def _request_assets(self, keys: list[str]) -> None:
        for key in keys:
            if key and key not in self.asset_attempted and self.asset_service.can_fetch(key):
                self.pending_asset_keys.add(key)
        if self.asset_thread is not None and self.asset_thread.isRunning():
            return
        if not self.pending_asset_keys:
            return

        batch = sorted(self.pending_asset_keys)[:10]
        for key in batch:
            self.pending_asset_keys.discard(key)
        self.asset_attempted.update(batch)
        self.asset_thread = QThread(self)
        worker = AssetBatchWorker(batch)
        worker.moveToThread(self.asset_thread)
        self.asset_thread.started.connect(worker.run)
        worker.finished.connect(self._assets_loaded)
        worker.finished.connect(self.asset_thread.quit)
        self.asset_thread.finished.connect(worker.deleteLater)
        self.asset_thread.finished.connect(self.asset_thread.deleteLater)
        self.asset_thread.start()
        self._asset_worker = worker

    def _assets_loaded(self, result: dict[str, str]) -> None:
        for key, path in result.items():
            self.cached_assets[key] = Path(path)
        self._render_home()
        self._render_bosses()
        self.asset_thread = None
        if self.pending_asset_keys:
            self._request_assets([])

    @staticmethod
    def _set_pixmap(label: QLabel, path: Path, size: int) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        label.setPixmap(scaled)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    @staticmethod
    def _next_kc_target(current: int) -> int:
        for milestone in [5, 10, 25, 50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000]:
            if milestone > current:
                return milestone
        return current + 1000
