"""Імітація роботи в окремому редакторі: «Редагувати текст» без запуску програми, правка DOCX, збереження."""
from unittest import mock

import docx


def edit_externally(ed, add: str = "", replace_body: str | None = None, title: str | None = None) -> bool:
    with mock.patch("nakazy.external_edit.open_file", lambda db, path: "тест"):
        ed.start_edit()
    d = docx.Document(ed.edit_file)
    if title is not None:
        d.paragraphs[0].text = title
    if replace_body is not None:
        for p in d.paragraphs[1:]:
            p._element.getparent().remove(p._element)
        d.add_paragraph(replace_body)
    if add:
        d.add_paragraph(add)
    d.save(ed.edit_file)
    return ed.sync_now()
