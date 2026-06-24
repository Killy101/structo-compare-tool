from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser, QTextEdit
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
  s, del, strike,
  span[style*="line-through"]       { text-decoration: line-through; }
  span[style*="underline"]          { text-decoration: underline; }

  span[style*="background:#ffb3b3"] { background: #ffb3b3; border-radius: 3px; }
  span[style*="background:#b3ffb3"] { background: #b3ffb3; border-radius: 3px; }
  span[style*="background:#ffffa0"] { background: #ffffa0; border-radius: 3px; }
  span[style*="background:#ffd6d6"] { background: #ffd6d6; border-radius: 3px; }
</style>
"""

_PLACEHOLDER = _CSS + """
<body>
  <p style="color:#aaa;font-style:italic;margin-top:20px">No document loaded.</p>
</body>
"""


class DocumentPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.browser = QTextBrowser()
        self.browser.setStyleSheet('background:#ffffff;border:none;')
        self.browser.setOpenLinks(False)
        self.browser.setHtml(_PLACEHOLDER)
        layout.addWidget(self.browser)

    def set_html(self, content: str):
        self.browser.setHtml(
            f'<html><head>{_CSS}</head><body>{content}</body></html>'
        )

    def scroll_to_anchor(self, anchor: str):
        if not anchor:
            return
        # Move the cursor to the named anchor so the view scrolls reliably,
        # then flash the surrounding line so the user sees where it landed.
        self.browser.scrollToAnchor(anchor)
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
                # frag.isValid() requires length > 0; our &#8203; anchor
                # satisfies that.  Check anchorNames regardless of length
                # so we degrade gracefully for any legacy empty anchors.
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
        self.browser.setHtml(_PLACEHOLDER)

    def scroll_fraction(self) -> float:
        sb = self.browser.verticalScrollBar()
        mx = sb.maximum()
        return sb.value() / mx if mx > 0 else 0.0

    def set_scroll_fraction(self, frac: float):
        sb = self.browser.verticalScrollBar()
        sb.setValue(int(sb.maximum() * frac))
