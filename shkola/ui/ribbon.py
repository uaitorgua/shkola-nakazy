"""Стрічка інструментів ГС «УАІТ» (власний макет): кнопка-меню «Документ», вкладки за шкільними завданнями,
швидкий доступ праворуч, згортання подвійним кліком; вкладки → групи з підписом знизу → великі кнопки
(іконка над текстом) і малі (іконка поруч із текстом або лише іконка), будь-які віджети (комбобокси, поля).

    rb = Ribbon()
    home = rb.tab("Основне")
    g = home.group("Шрифт")
    g.big("Жирний", "bold", slot, checkable=True)
    g.small("Курсив", "italic", slot)
    g.widget(combo)
    g.column(a1, a2, a3)          # три малі дії стовпчиком
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFrame, QMenu, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QTabWidget, QToolButton,
                               QVBoxLayout, QWidget)

from . import icons, theme

BIG, SMALL = 28, 18
QUICK_ICONS = {"Ctrl+S": "save", "Ctrl+Z": "undo", "Ctrl+Y": "redo", "Ctrl+P": "print"}


class RibbonGroup(QFrame):
    def __init__(self, title: str, owner) -> None:
        super().__init__()
        self.setObjectName("rgroup")
        self.owner = owner
        self.row = QHBoxLayout()
        self.row.setContentsMargins(6, 4, 6, 0)
        self.row.setSpacing(4)
        self.row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        cap = QLabel(title)
        cap.setObjectName("rcaption")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 2)
        lay.setSpacing(0)
        lay.addLayout(self.row, 1)
        lay.addWidget(cap)

    # ---------- дії ----------
    def _action(self, text, icon, slot, key=None, checkable=False, tip=None) -> QAction:
        a = QAction(text, self.owner)
        if slot is not None:
            a.triggered.connect(slot)
        if key:
            a.setShortcut(QKeySequence(key))
        a.setCheckable(checkable)
        a.setToolTip((tip or text) + (f"  ({key})" if key else ""))
        if icon and icons.available():
            a.setIcon(icons.icon(icon))
        a.setData(icon)
        self.owner.addAction(a)            # ярлики працюють у всьому вікні
        return a

    def _button(self, a: QAction, big: bool, text: bool = True) -> QToolButton:
        b = QToolButton()
        b.setDefaultAction(a)
        b.setAutoRaise(True)
        b.setObjectName("rbig" if big else "rsmall")
        b.setIconSize(QSize(BIG, BIG) if big else QSize(SMALL, SMALL))
        if big:
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setMinimumWidth(56)
            b.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        else:
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text and not (a.icon().isNull() is False and not text)
                                 else Qt.ToolButtonStyle.ToolButtonIconOnly)
            if not text:
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            b.setFixedHeight(24)
        if a.icon().isNull():
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        return b

    def big(self, text, icon, slot, key=None, checkable=False, tip=None) -> QAction:
        a = self._action(text, icon, slot, key, checkable, tip)
        self.row.addWidget(self._button(a, True))
        return a

    def small(self, text, icon, slot, key=None, checkable=False, tip=None, text_visible=False) -> QAction:
        a = self._action(text, icon, slot, key, checkable, tip)
        self.row.addWidget(self._button(a, False, text_visible))
        return a

    def column(self, *actions: QAction, text_visible: bool = True) -> None:
        """До трьох малих дій стовпчиком."""
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        for a in actions:
            col.addWidget(self._button(a, False, text_visible))
        col.addStretch(1)
        self.row.addLayout(col)

    def small_row(self, *actions: QAction) -> None:
        """Малі дії в один ряд (лише іконки)."""
        r = QHBoxLayout()
        r.setContentsMargins(0, 0, 0, 0)
        r.setSpacing(1)
        for a in actions:
            r.addWidget(self._button(a, False, False))
        w = QWidget()
        w.setLayout(r)
        self.row.addWidget(w, 0, Qt.AlignmentFlag.AlignTop)

    def grid(self, rows: list[list[QAction]]) -> None:
        """Сітка малих дій (лише іконки), напр. 2 ряди по 4."""
        g = QGridLayout()
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(1)
        for i, row in enumerate(rows):
            for j, a in enumerate(row):
                g.addWidget(self._button(a, False, False), i, j)
        w = QWidget()
        w.setLayout(g)
        self.row.addWidget(w, 0, Qt.AlignmentFlag.AlignTop)

    def action(self, text, icon, slot, key=None, checkable=False, tip=None) -> QAction:
        """Дія без кнопки (для column/grid/small_row)."""
        return self._action(text, icon, slot, key, checkable, tip)

    def widget(self, w: QWidget, align_top: bool = True) -> QWidget:
        self.row.addWidget(w, 0, Qt.AlignmentFlag.AlignTop if align_top else Qt.AlignmentFlag.AlignVCenter)
        return w

    def vwidgets(self, *ws: QWidget) -> None:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        for w in ws:
            col.addWidget(w)
        col.addStretch(1)
        self.row.addLayout(col)


class RibbonTab(QWidget):
    def __init__(self, owner) -> None:
        super().__init__()
        self.owner = owner
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(6, 2, 6, 2)
        self.lay.setSpacing(4)
        self.lay.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def group(self, title: str) -> RibbonGroup:
        g = RibbonGroup(title, self.owner)
        if self.lay.count():
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setObjectName("rsep")
            self.lay.addWidget(sep)
        self.lay.addWidget(g)
        return g


class Ribbon(QTabWidget):
    def __init__(self, owner) -> None:
        super().__init__()
        self.owner = owner
        self.setObjectName("ribbon")
        self.setDocumentMode(True)
        self.setFixedHeight(126)
        self.collapsed = False
        self.tabBar().tabBarDoubleClicked.connect(lambda _i: self.toggle())
        self.tabBar().tabBarClicked.connect(lambda _i: self.collapsed and self.toggle())

    def toggle(self) -> None:
        """Згорнути/розгорнути стрічку (лишаються самі вкладки)."""
        self.collapsed = not self.collapsed
        self.setFixedHeight(self.tabBar().sizeHint().height() + 2 if self.collapsed else 126)
        if hasattr(self, "btn_fold"):
            self.btn_fold.setText("▾" if self.collapsed else "▴")

    def finish(self, menubar, quick_keys=("Ctrl+S", "Ctrl+Z", "Ctrl+Y", "Ctrl+P")) -> None:
        """Меню вікна переходить у кнопку «Документ» ліворуч від вкладок; праворуч — швидкий доступ і згортання."""
        menus = [a.menu() for a in menubar.actions() if a.menu()]
        doc = QMenu(self.owner)
        if menus:
            doc.addActions(menus[0].actions())
            for m in menus[1:]:
                doc.addSeparator()
                doc.addMenu(m)
        b = QToolButton()
        b.setObjectName("rdoc")
        b.setText("Документ ▾")
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        b.setMenu(doc)
        self.btn_doc = b
        self.setCornerWidget(b, Qt.Corner.TopLeftCorner)
        menubar.hide()
        qa = QWidget()
        ql = QHBoxLayout(qa)
        ql.setContentsMargins(0, 0, 4, 0)
        ql.setSpacing(1)
        acts = {a.shortcut().toString(): a for a in self.owner.findChildren(QAction) if not a.shortcut().isEmpty()}
        for k in quick_keys:
            a = acts.get(k)
            if a is not None:
                q = QToolButton()
                q.setObjectName("rquick")
                q.setAutoRaise(True)
                q.setIcon(icons.icon(QUICK_ICONS.get(k, "check")))
                q.setToolTip(f"{a.text().replace('&', '')}  ({k})")
                q.clicked.connect(a.trigger)
                q.setIconSize(QSize(16, 16))
                ql.addWidget(q)
        self.btn_fold = QToolButton()
        self.btn_fold.setObjectName("rquick")
        self.btn_fold.setAutoRaise(True)
        self.btn_fold.setText("▴")
        self.btn_fold.setToolTip("Згорнути або розгорнути стрічку (подвійний клік по вкладці)")
        self.btn_fold.clicked.connect(self.toggle)
        ql.addWidget(self.btn_fold)
        self.setCornerWidget(qa, Qt.Corner.TopRightCorner)

    def tab(self, title: str) -> RibbonTab:
        t = RibbonTab(self.owner)
        self.addTab(t, title)
        return t


RIBBON_STYLE = f"""
QTabWidget#ribbon::pane {{ border: none; border-bottom: 1px solid {theme.LINE}; background: #fbfcfc; top: 0; }}
QTabWidget#ribbon > QTabBar::tab {{ background: transparent; border: none; padding: 5px 14px; margin: 0;
    color: {theme.GRAPHITE}; font-weight: 600; font-size: 10pt; }}
QTabWidget#ribbon > QTabBar::tab:selected {{ color: {theme.PRIMARY_DARK}; border-bottom: 3px solid {theme.ACCENT}; background: #fbfcfc; }}
QTabWidget#ribbon > QTabBar::tab:hover {{ color: {theme.PRIMARY}; }}
QToolButton#rdoc {{ background: {theme.PRIMARY}; color: white; font-weight: 700; padding: 4px 12px; margin: 2px 8px 2px 4px;
    border-radius: 6px; border: none; }}
QToolButton#rdoc:hover {{ background: {theme.PRIMARY_DARK}; }}
QToolButton#rdoc::menu-indicator {{ image: none; }}
QToolButton#rquick {{ padding: 2px; border-radius: 4px; color: {theme.GRAPHITE}; }}
QToolButton#rquick:hover {{ background: {theme.PRIMARY_LIGHT}; }}
QFrame#rgroup {{ background: transparent; }}
QFrame#rsep {{ color: {theme.LINE}; }}
QLabel#rcaption {{ color: {theme.MUTED}; font-size: 8pt; padding-top: 2px; }}
QToolButton#rbig {{ color: {theme.TEXT}; font-size: 8.5pt; padding: 2px 4px; border-radius: 6px; border: 1px solid transparent; }}
QToolButton#rsmall {{ color: {theme.TEXT}; font-size: 9pt; padding: 1px 4px; border-radius: 4px; border: 1px solid transparent; }}
QToolButton#rbig:hover, QToolButton#rsmall:hover {{ background: {theme.PRIMARY_LIGHT}; border-color: #b9d6cc; }}
QToolButton#rbig:checked, QToolButton#rsmall:checked {{ background: {theme.ACCENT}; border-color: #c98f2e; }}
QToolButton#rbig:pressed, QToolButton#rsmall:pressed {{ background: #cfe5dd; }}
QToolButton#rbig:disabled, QToolButton#rsmall:disabled {{ color: #a9b4b0; }}
QTabWidget#ribbon QComboBox, QTabWidget#ribbon QFontComboBox, QTabWidget#ribbon QSpinBox, QTabWidget#ribbon QLineEdit {{ min-height: 20px; padding: 2px 4px; }}
"""
