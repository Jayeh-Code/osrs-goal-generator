APP_STYLESHEET = r"""
QMainWindow, QWidget {
    background: #071117;
    color: #e8edf0;
    font-size: 13px;
}
QToolTip {
    background: #10212b;
    color: #eef4f6;
    border: 1px solid #496575;
    padding: 5px 7px;
}
QFrame#Sidebar {
    background: #071016;
    border-right: 2px solid #263843;
}
QFrame#TopBar {
    background: #09151d;
    border-bottom: 1px solid #2a414f;
}
QFrame#TopStatStrip {
    background: #0b1820;
    border: 1px solid #2a4352;
    border-radius: 9px;
}
QFrame#Card, QFrame#DashboardCard {
    background: #0c1a23;
    border: 1px solid #2b4454;
    border-radius: 10px;
}
QFrame#ElevatedCard {
    background: #0f202a;
    border: 1px solid #38586a;
    border-radius: 11px;
}
QFrame#AccentCard {
    background: #10241d;
    border: 1px solid #3b7451;
    border-radius: 11px;
}
QFrame#HeroCard, QFrame#DashboardHero {
    background: #0a1a24;
    border: 1px solid #3b5969;
    border-radius: 11px;
}
QFrame#HeroControls, QFrame#GoalPanel {
    background: rgba(5, 17, 24, 0.86);
    border: 1px solid #294758;
    border-radius: 9px;
}
QFrame#StatTile, QFrame#OverviewTile {
    background: #0a171f;
    border: 1px solid #294453;
    border-radius: 8px;
}
QFrame#PathCard, QFrame#DiaryCard, QFrame#CollectionCard {
    background: #0d1d27;
    border: 1px solid #304d5d;
    border-radius: 10px;
}
QFrame#PathCard:hover, QFrame#DiaryCard:hover, QFrame#CollectionCard:hover {
    border-color: #4d7183;
    background: #10222d;
}
QFrame#SkillRow {
    background: transparent;
    border-bottom: 1px solid #1c3441;
}
QFrame#InsetPanel, QLabel#InsetPanel, QLabel#SpriteWell {
    background: #07131a;
    border: 1px solid #284554;
    border-radius: 8px;
}
QPushButton#NavButton {
    text-align: left;
    padding: 11px 13px;
    margin: 1px 0;
    border: 1px solid transparent;
    border-radius: 6px;
    color: #c2cbd0;
    font-weight: 600;
}
QPushButton#NavButton:hover {
    background: #102532;
    border-color: #27495b;
    color: #ffffff;
}
QPushButton#NavButton:checked {
    background: #17618f;
    border-left: 4px solid #65e292;
    border-color: #2d80ad;
    color: #ffffff;
}
QPushButton#Primary {
    background: #17984a;
    border: 1px solid #38ca70;
    border-radius: 7px;
    padding: 9px 14px;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#Primary:hover { background: #20ad58; }
QPushButton#Primary:disabled {
    background: #183126;
    border-color: #2b5040;
    color: #71827b;
}
QPushButton#HeroGenerate {
    background: #16a34a;
    border: 2px solid #56e287;
    border-radius: 9px;
    padding: 14px 22px;
    color: #ffffff;
    font-size: 22px;
    font-weight: 900;
}
QPushButton#HeroGenerate:hover { background: #1db759; }
QPushButton#HeroGenerate:disabled {
    background: #173626;
    border-color: #2c5a42;
    color: #80948a;
}
QPushButton#GoldButton {
    background: #8d671e;
    border: 1px solid #d0a445;
    border-radius: 7px;
    padding: 9px 14px;
    color: #fff4c9;
    font-weight: 700;
}
QPushButton#GoldButton:hover { background: #a77923; }
QPushButton#Secondary {
    background: #112532;
    border: 1px solid #35576a;
    border-radius: 7px;
    padding: 8px 12px;
    color: #d9e3e8;
    font-weight: 600;
}
QPushButton#Secondary:hover {
    background: #173342;
    border-color: #4e7a90;
}
QPushButton#Danger {
    background: #492522;
    border: 1px solid #934b43;
    border-radius: 7px;
    padding: 8px 12px;
    color: #ffd2cb;
    font-weight: 600;
}
QPushButton#Danger:hover { background: #5d2d29; }
QPushButton#LinkButton {
    background: transparent;
    border: 0;
    color: #5cb9f0;
    padding: 4px 6px;
    font-weight: 700;
}
QPushButton#LinkButton:hover { color: #91d6ff; }
QLineEdit, QComboBox, QListWidget, QTableWidget, QSpinBox, QTextEdit {
    background: #07151d;
    border: 1px solid #2e4b5b;
    border-radius: 6px;
    padding: 7px;
    color: #edf4f6;
    selection-background-color: #17618f;
    selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #5c9bb9;
}
QComboBox::drop-down {
    border: 0;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: #0d1d27;
    border: 1px solid #365669;
    selection-background-color: #17618f;
}
QTableWidget {
    gridline-color: #1d3440;
    alternate-background-color: #091820;
}
QTableWidget::item {
    padding: 7px 5px;
    border-bottom: 1px solid #1b3441;
}
QTableWidget::item:selected {
    background: #184f6e;
    color: #ffffff;
}
QHeaderView::section {
    background: #10232e;
    color: #edd9a6;
    padding: 9px 7px;
    border: 0;
    border-right: 1px solid #254453;
    border-bottom: 1px solid #3e6577;
    font-weight: 700;
}
QScrollArea {
    border: 0;
    background: transparent;
}
QScrollBar:vertical {
    background: #071117;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #345362;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #4a7082; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLabel#Brand {
    font-size: 18px;
    font-weight: 900;
    color: #efd07c;
}
QLabel#BrandSub {
    font-size: 10px;
    color: #87949a;
}
QLabel#Title {
    font-size: 25px;
    font-weight: 800;
    color: #f0d9a2;
}
QLabel#HeroHeading {
    font-size: 30px;
    font-weight: 900;
    color: #f3dfae;
}
QLabel#HeroSub {
    color: #b7c4ca;
    font-size: 13px;
}
QLabel#PageEyebrow {
    font-size: 10px;
    font-weight: 800;
    color: #90a0a8;
}
QLabel#SectionTitle {
    font-size: 17px;
    font-weight: 800;
    color: #f0d9a2;
}
QLabel#CardTitle {
    font-size: 12px;
    font-weight: 800;
    color: #e4d3aa;
}
QLabel#GoalTitle {
    font-size: 24px;
    font-weight: 800;
    color: #ffffff;
}
QLabel#HeroValue {
    font-size: 26px;
    font-weight: 800;
    color: #ffffff;
}
QLabel#StatValue {
    font-size: 18px;
    font-weight: 800;
    color: #ffffff;
}
QLabel#StatLabel {
    font-size: 10px;
    font-weight: 700;
    color: #94a3aa;
}
QLabel#OverviewGlyph {
    font-size: 18px;
    color: #e8c86f;
    font-weight: 900;
}
QLabel#Muted { color: #94a3aa; }
QLabel#Success { color: #61dc8d; font-weight: 700; }
QLabel#Warning { color: #efc463; font-weight: 700; }
QLabel#DangerText { color: #f08d82; font-weight: 700; }
QLabel#Pill {
    background: #123523;
    border: 1px solid #2b8a52;
    border-radius: 8px;
    padding: 3px 8px;
    color: #78e7a2;
    font-size: 10px;
    font-weight: 800;
}
QLabel#GoldPill {
    background: #332912;
    border: 1px solid #82682d;
    border-radius: 8px;
    padding: 3px 8px;
    color: #efd16f;
    font-size: 10px;
    font-weight: 800;
}
QProgressBar {
    border: 1px solid #2d4857;
    border-radius: 6px;
    background: #071218;
    text-align: center;
    color: #dfe8ec;
    min-height: 16px;
    font-size: 10px;
    font-weight: 700;
}
QProgressBar::chunk {
    background: #56cc89;
    border-radius: 5px;
}
QListWidget::item {
    padding: 6px 4px;
    border-bottom: 1px solid #1d3643;
}
QListWidget::item:selected { background: #174a67; }
QDialog { background: #08151c; }
QDialogButtonBox QPushButton {
    min-width: 92px;
    padding: 8px 12px;
}
"""
