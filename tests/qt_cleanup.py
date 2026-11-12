"""Акуратне завершення Qt у тестах: закрити й знищити всі вікна до виходу інтерпретатора
(інакше Python іноді руйнує віджети після QApplication -> падіння 0xC0000409 при виході)."""


def tearDownModule():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        w.close()
        w.deleteLater()
    for _ in range(3):
        app.processEvents()
