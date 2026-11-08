"""Стиль «Сканер ШКОЛА»: спокійна зелено-графітова гама, бурштиновий акцент, білі картки."""

PRIMARY = "#1d7a66"        # основний зелений (смарагд)
PRIMARY_DARK = "#135548"
PRIMARY_LIGHT = "#e3f1ec"
ACCENT = "#f0b14a"         # бурштиновий акцент
GRAPHITE = "#2c3137"
BG = "#eef1f0"
PANEL = "#ffffff"
LINE = "#d3dbd8"
TEXT = "#1b1f23"
MUTED = "#5d6670"
OK, WARN, BAD = "#15803d", "#b45309", "#b91c1c"
VIEW_BG = "#353b42"

# Сумісні назви для спільних віджетів
NAVY, NAVY_DARK, NAVY_LIGHT, GOLD = PRIMARY, PRIMARY_DARK, PRIMARY_LIGHT, ACCENT

STYLE = f"""
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; font-family: 'e-Ukraine', 'Segoe UI'; font-size: 10pt; }}
QScrollArea {{ border: none; background: {BG}; }}
QScrollArea > QWidget > QWidget {{ background: {BG}; }}

QGroupBox {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px;
            margin-top: 22px; padding: 14px 10px 10px 10px; font-weight: 700; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; top: 2px; padding: 2px 8px;
                   color: white; background: {PRIMARY}; border-radius: 4px; }}

QPushButton {{ background: {PANEL}; border: 1px solid #b7c4bf; border-radius: 6px; padding: 6px 10px; }}
QPushButton:hover {{ border-color: {PRIMARY}; background: {PRIMARY_LIGHT}; }}
QPushButton:pressed {{ background: #cfe5dd; }}
QPushButton:disabled {{ color: #9aa5a1; border-color: {LINE}; background: #f5f7f6; }}
QPushButton#primary {{ background: {PRIMARY}; color: white; border: none; font-weight: 700; padding: 9px 14px; }}
QPushButton#primary:hover {{ background: {PRIMARY_DARK}; }}
QPushButton#primary:disabled {{ background: #9ec2b7; }}
QPushButton#accent {{ background: {ACCENT}; color: {TEXT}; border: none; font-weight: 700; padding: 9px 14px; }}
QPushButton#accent:hover {{ background: #e5a338; }}
QPushButton:checked {{ background: {ACCENT}; border-color: #c98f2e; color: {TEXT}; }}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background: white; border: 1px solid #b7c4bf;
            border-radius: 5px; padding: 4px 6px; min-height: 20px; }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{ border: 2px solid {PRIMARY}; }}
QRadioButton::indicator:checked, QCheckBox::indicator:checked {{ background: {PRIMARY}; border: 2px solid {PRIMARY}; border-radius: 3px; }}

QListWidget {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 8px; padding: 4px; }}
QListWidget::item {{ padding: 4px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {PRIMARY_LIGHT}; color: {TEXT}; border: 2px solid {PRIMARY}; }}
QListWidget#strip {{ background: {GRAPHITE}; border: none; border-top: 3px solid {ACCENT}; border-radius: 0; }}
QListWidget#strip::item {{ color: #d8dedb; }}
QListWidget#strip::item:selected {{ background: #41494f; color: white; border: 2px solid {ACCENT}; }}

QToolBar {{ background: {PANEL}; border-bottom: 1px solid {LINE}; spacing: 2px; padding: 3px 8px; }}
QToolBar QToolButton {{ color: {PRIMARY_DARK}; padding: 5px 9px; border-radius: 5px; font-weight: 600; }}
QToolBar QToolButton:hover {{ background: {PRIMARY_LIGHT}; }}
QToolBar QToolButton:checked {{ background: {ACCENT}; }}
QToolBar::separator {{ background: {LINE}; width: 1px; margin: 4px 6px; }}

QStatusBar {{ background: {GRAPHITE}; color: white; }}
QStatusBar QLabel {{ color: white; }}
QProgressBar {{ border: 1px solid {LINE}; border-radius: 5px; text-align: center; background: white; }}
QProgressBar::chunk {{ background: {PRIMARY}; border-radius: 4px; }}

QSlider::handle:horizontal {{ background: {PRIMARY}; width: 16px; margin: -6px 0; border-radius: 8px; border: 2px solid white; }}
QSlider::groove:horizontal {{ height: 4px; background: #c9d4d0; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {PRIMARY}; border-radius: 2px; }}

QLabel#header {{ color: white; font-size: 14pt; font-weight: 700; }}
QLabel#subheader {{ color: {ACCENT}; font-weight: 600; letter-spacing: 1px; }}
QLabel#hint {{ color: {MUTED}; font-size: 9pt; }}
QWidget#zoombar {{ background: {PANEL}; border-top: 1px solid {LINE}; }}
QLabel#muted {{ color: {MUTED}; }}
QTabWidget::pane {{ border: 1px solid {LINE}; border-radius: 6px; top: -1px; background: white; }}
QTabBar::tab {{ background: {BG}; border: 1px solid {LINE}; padding: 6px 14px; margin-right: 2px;
               border-top-left-radius: 6px; border-top-right-radius: 6px; color: {MUTED}; font-weight: 600; }}
QTabBar::tab:selected {{ background: white; color: {PRIMARY_DARK}; border-bottom: 3px solid {ACCENT}; }}
QTextEdit, QPlainTextEdit {{ background: white; border: 1px solid {LINE}; border-radius: 6px; }}
QTableWidget {{ background: white; gridline-color: {LINE}; border: 1px solid {LINE}; }}
QHeaderView::section {{ background: {PRIMARY_LIGHT}; color: {PRIMARY_DARK}; border: 1px solid {LINE}; padding: 4px; font-weight: 600; }}
QToolTip {{ background: {GRAPHITE}; color: white; border: none; padding: 5px; }}

/* ── Редактори InterText / InterTab ── */
QToolBar#editorbar {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #eef5f2);
                      border: none; border-bottom: 1px solid {LINE}; spacing: 3px; padding: 4px 8px; }}
QToolBar#editorbar QToolButton {{ color: {PRIMARY_DARK}; padding: 5px 8px; border-radius: 6px; min-width: 24px; min-height: 22px; font-weight: 600; }}
QToolBar#editorbar QToolButton:hover {{ background: {PRIMARY_LIGHT}; color: {PRIMARY_DARK}; border: 1px solid #b9d6cc; }}
QToolBar#editorbar QToolButton:checked {{ background: {ACCENT}; color: {TEXT}; border: 1px solid #c98f2e; }}
QToolBar#editorbar QToolButton:pressed {{ background: #cfe5dd; }}
QMenuBar {{ background: {GRAPHITE}; color: white; padding: 2px 6px; }}
QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {PRIMARY}; }}
QMenu {{ background: white; border: 1px solid {LINE}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {PRIMARY_LIGHT}; color: {PRIMARY_DARK}; }}
QTableWidget {{ selection-background-color: {PRIMARY_LIGHT}; selection-color: {TEXT}; }}
QTableCornerButton::section {{ background: {PRIMARY_LIGHT}; border: 1px solid {LINE}; }}
QToolBar#editorbar QToolButton:pressed {{ background: #cfe5dd; }}
QToolBar#editorbar::separator {{ background: {LINE}; width: 1px; margin: 4px 5px; }}
QToolBar#editorbar QComboBox, QToolBar#editorbar QFontComboBox, QToolBar#editorbar QSpinBox {{ min-height: 24px; }}

QWidget#canvas {{ background: {VIEW_BG}; }}
QScrollArea#canvas {{ background: {VIEW_BG}; border: none; }}
QScrollArea#canvas > QWidget > QWidget {{ background: {VIEW_BG}; }}

QLineEdit#namebox {{ background: white; border: 1px solid #b7c4bf; border-right: 2px solid {PRIMARY};
                    border-radius: 5px; padding: 4px 6px; font-weight: 700; color: {PRIMARY_DARK};
                    min-width: 72px; max-width: 92px; }}
QLineEdit#formulabar {{ background: white; border: 1px solid #b7c4bf; border-radius: 5px; padding: 5px 8px; }}
QLineEdit#formulabar:focus {{ border: 2px solid {PRIMARY}; }}
QWidget#formularow {{ background: {PANEL}; border-bottom: 1px solid {LINE}; }}
QLabel#fx {{ color: {MUTED}; font-style: italic; font-weight: 700; padding: 0 4px; }}

QTabWidget#sheets::pane {{ border: 1px solid {LINE}; border-radius: 0; top: 0; background: white; }}
QTabWidget#sheets QTabBar::tab {{ background: {BG}; border: 1px solid {LINE}; padding: 5px 16px; margin-right: 2px;
               border-bottom-left-radius: 6px; border-bottom-right-radius: 6px;
               border-top-left-radius: 0; border-top-right-radius: 0; color: {MUTED}; font-weight: 600; }}
QTabWidget#sheets QTabBar::tab:selected {{ background: white; color: {PRIMARY_DARK}; border-top: 3px solid {ACCENT}; }}
"""
