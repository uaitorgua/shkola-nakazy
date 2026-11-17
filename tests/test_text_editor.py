"""Вбудований простий редактор наказу: форматування, вирівнювання, відступи, списки, таблиці, поля сторінки.
Усе зберігається в базу й правильно переходить у DOCX наказу (export) та в «Відкрити в іншій програмі»."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["NAKAZY_OFFLINE"] = "1"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QTextBlockFormat, QTextCharFormat, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from nakazy.db import Database  # noqa: E402
from nakazy.ui.order_editor import OrderEditor, create_from_template  # noqa: E402
from nakazy.ui.text_editor import MARGINS, MM, TextEditor  # noqa: E402


class TextEditorTest(unittest.TestCase):
    def test_page_margins(self):
        from nakazy.export import MARGINS as EXPORT_MARGINS
        self.assertEqual(MARGINS, EXPORT_MARGINS)  # поля в редакторі = поля збереженого наказу
        t = TextEditor("<p>Текст</p>")
        m = t.page.layout().contentsMargins()  # поля аркуша A4
        self.assertEqual((m.left(), m.right()), (int(30 * MM), int(10 * MM)))
        self.assertNotIn("-qt-table-type: root", t.html())  # поля не потрапляють у текст наказу
        self.assertFalse(t.isModified())
        t.close()

    def test_format_and_docx(self):
        import docx
        d = tempfile.mkdtemp(); db = Database(os.path.join(d, "t.db")); db.set_setting("head", "Олена ПЕТРЕНКО")
        oid = create_from_template(db, "o_free", {"subject": "чергування", "preamble": "З метою порядку"})
        ed = OrderEditor(db, oid); t = ed.text; e = t.edit
        def new_par(text):
            c = e.textCursor(); c.movePosition(QTextCursor.End); c.insertBlock(QTextBlockFormat(), QTextCharFormat())
            c.insertText(text); c.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor); e.setTextCursor(c)
        new_par("Жирний по центру"); t._char(bold=True); e.setAlignment(Qt.AlignHCenter)
        new_par("Абзац з відступом"); e.setAlignment(Qt.AlignJustify); t._first_line(True); t._indent(1)
        new_par("")
        table = t.insert_table(2, 3)
        table.cellAt(0, 0).firstCursorPosition().insertText("№")
        table.cellAt(0, 1).firstCursorPosition().insertText("ПІБ")
        table.cellAt(1, 1).firstCursorPosition().insertText("Коваль М. І.")
        e.setTextCursor(table.cellAt(1, 1).firstCursorPosition()); t._table("row+"); t._table("col+")
        self.assertEqual((table.rows(), table.columns()), (3, 4))
        e.setTextCursor(table.cellAt(2, 3).firstCursorPosition()); t._table("row-"); t._table("col-")
        self.assertEqual((table.rows(), table.columns()), (2, 3))
        self.assertTrue(t.isModified())
        ed.save_order()
        self.assertFalse(t.isModified())
        body = db.get(oid)["body_html"]
        self.assertIn("Коваль М. І.", body); self.assertIn("text-indent", body)
        # збережений наказ (DOCX з бланком): таблиця, жирний, центр, відступи
        from nakazy.export import export_docx
        out = os.path.join(d, "n.docx"); export_docx(db, oid, out)
        doc = docx.Document(out)
        self.assertTrue(any(tb.cell(1, 1).text == "Коваль М. І." for tb in doc.tables))
        p = next(p for p in doc.paragraphs if p.text == "Жирний по центру")
        self.assertTrue(all(r.bold for r in p.runs if r.text.strip())); self.assertEqual(p.alignment, 1)
        p = next(p for p in doc.paragraphs if p.text == "Абзац з відступом")
        self.assertGreater(p.paragraph_format.first_line_indent or 0, 0)
        self.assertGreater(p.paragraph_format.left_indent or 0, 0)
        # «Відкрити в іншій програмі» і назад: таблиця й текст не губляться
        from nakazy import external_edit as ee
        path = ee.write_docx(db, oid)
        dd = docx.Document(path); dd.add_paragraph("Ще пункт."); dd.save(path)
        self.assertTrue(ee.sync(db, oid, path))
        body = db.get(oid)["body_html"]
        for s in ("Ще пункт.", "Коваль М. І.", "<table", "Жирний по центру"):
            self.assertIn(s, body)
        ed._closed = True; ed.close(); db.close()

    def test_list_toggle_and_readonly(self):
        from PySide6.QtGui import QTextListFormat
        t = TextEditor("<p>Перший</p>")
        t._list(QTextListFormat.ListDecimal); self.assertIsNotNone(t.edit.textCursor().currentList())
        t._list(QTextListFormat.ListDecimal); self.assertIsNone(t.edit.textCursor().currentList())
        t.setReadOnly(True); self.assertTrue(t.edit.isReadOnly()); self.assertFalse(t.bar.isEnabled())
        t.close()


from qt_cleanup import tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
