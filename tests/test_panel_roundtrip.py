"""Round-trip test: editing then Re-Compare must preserve word emphasis.

Requires a Qt application; skipped automatically if PySide6 / a Qt platform
plugin is unavailable.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    inst = QApplication.instance() or QApplication([])
    yield inst


def test_edited_document_preserves_emphasis_and_indent(app):
    from ui.document_panel import DocumentPanel

    panel = DocumentPanel()
    panel.set_html(
        '<p>&nbsp;&nbsp;&nbsp;&nbsp;<a name="c1">&#8203;</a>keep '
        '<span style="text-decoration:line-through;color:#888">repealed</span> '
        '<span style="font-weight:bold">bold</span> '
        '<span style="font-style:italic">it</span> '
        '<span style="text-decoration:underline">und</span></p>'
    )
    doc = panel.edited_document()

    assert len(doc.blocks) == 1
    block = doc.blocks[0]
    assert block.indent == 4                       # &nbsp; padding recovered
    flags = {s.text.strip(): (s.bold, s.italic, s.underline, s.strikethrough)
             for s in block.spans}
    assert flags["repealed"] == (False, False, False, True)
    assert flags["bold"] == (True, False, False, False)
    assert flags["it"] == (False, True, False, False)
    assert flags["und"] == (False, False, True, False)
