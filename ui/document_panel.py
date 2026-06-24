from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from PySide6.QtGui import QTextCursor, QColor
from PySide6.QtCore import Qt, QTimer

_CSS = """
<style>
  body {
    font-family: Arial, sans-serif;
    font-size: 13px;
    line-height: 1.65;
    padding: 14px;
    color: #1a1a1a;
    background: #ffffff;
  }
  p { margin: 4px 0; }

  b, strong,
  span[style*="font-weight:bold"]   { font-weight: bold; }
  i, em,
  span[style*="font-style:italic"]  { font-style: italic; }

  /* Source-PDF text decorations — inline styles carry the authoritative value;
     these rules are fallbacks for Qt's renderer.  The combined rule must come
     LAST so it wins when both decorations are present (higher specificity via
     two attribute selectors). */
  s, del, strike                    { text-decoration: line-through; }
  span[style*="line-through"]       { text-decoration: line-through; }
  span[style*="underline"]          { text-decoration: underline; }
  span[style*="underline"][style*="line-through"] {
    text-decoration: underline line-through;
  }

  span[style*="background:#ffb3b3"] { background: #ffb3b3; border-radius: 3px; }
  span[style*="background:#b3ffb3"] { background: #b3ffb3; border-radius: 3px; }
</style>
"""

_PLACEHOLDER = _CSS + """
<body>
  <p style="color:#aaa;font-style:italic;margin-top:20px">No document loaded.</p>
</body>
"""

_STYLE_VIEW = 'background:#ffffff;border:none;'
_STYLE_EDIT = (
    'QTextEdit{background:#f8fafc;color:#1e293b;border:none;'
    'font-family:"Consolas","Courier New",monospace;font-size:12px;'
    'line-height:1.6;padding:10px;}'
)


class DocumentPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.browser = QTextEdit()
        self.browser.setReadOnly(True)
        self.browser.setStyleSheet(_STYLE_VIEW)
        self.browser.setHtml(_PLACEHOLDER)
        layout.addWidget(self.browser)

    def set_html(self, content: str):
        self.browser.setReadOnly(True)
        self.browser.setStyleSheet(_STYLE_VIEW)
        self.browser.setHtml(
            f'<html><head>{_CSS}</head><body>{content}</body></html>'
        )

    def set_editable(self, text: str):
        """Switch panel to plain-text editing mode — user can click anywhere and type."""
        self.browser.setReadOnly(False)
        self.browser.setStyleSheet(_STYLE_EDIT)
        self.browser.setPlainText(text)

    def scroll_to_anchor(self, anchor: str):
        if not anchor:
            return
        cursor = self._cursor_at_anchor(anchor)
        if cursor is not None:
            self.browser.setTextCursor(cursor)
            self.browser.ensureCursorVisible()
            self._flash(cursor)

    def _cursor_at_anchor(self, anchor: str):
        """Find a text cursor positioned at the block carrying the anchor name.

        The anchor element contains a zero-width space (U+200B) so that Qt
        creates a real text fragment for it — empty <a name> elements have no
        fragment and are never found by this walk.
        """
        doc = self.browser.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fmt = frag.charFormat()
                if fmt.isAnchor():
                    names = fmt.anchorNames()
                    if anchor in names:
                        c = self.browser.textCursor()
                        c.setPosition(frag.position())
                        return c
                it += 1
            block = block.next()
        return None

    def _flash(self, cursor: QTextCursor):
        sel = QTextEdit.ExtraSelection()
        flash_cursor = QTextCursor(cursor)
        flash_cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        sel.cursor = flash_cursor
        sel.format.setBackground(QColor('#fff3a0'))
        sel.format.setProperty(0x100000 + 1, True)  # FullWidthSelection
        self.browser.setExtraSelections([sel])
        QTimer.singleShot(1300, lambda: self.browser.setExtraSelections([]))

    def clear(self):
        self.browser.setReadOnly(True)
        self.browser.setStyleSheet(_STYLE_VIEW)
        self.browser.setHtml(_PLACEHOLDER)

    def scroll_fraction(self) -> float:
        sb = self.browser.verticalScrollBar()
        mx = sb.maximum()
        return sb.value() / mx if mx > 0 else 0.0

    def set_scroll_fraction(self, frac: float):
        sb = self.browser.verticalScrollBar()
        sb.setValue(int(sb.maximum() * frac))
