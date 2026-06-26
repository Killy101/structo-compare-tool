# ui/document_panel.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit
from PySide6.QtGui import QTextCursor, QColor
from PySide6.QtCore import Qt, QTimer

from models.document import Document, TextBlock, TextSpan

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

  s, del, strike                    { text-decoration: line-through; }
  span[style*="line-through"]       { text-decoration: line-through; }
  span[style*="underline"]          { text-decoration: underline; }
  span[style*="underline"][style*="line-through"] {
    text-decoration: underline line-through;
  }

  span[style*="color:#c0392b"] { color: #c0392b; }
  span[style*="color:#1a7a3c"] { color: #1a7a3c; }
</style>
"""

_PLACEHOLDER = _CSS + """
<body>
  <p style="color:#aaa;font-style:italic;margin-top:20px">No document loaded.</p>
</body>
"""

_STYLE_VIEW = 'background:#ffffff;border:none;'

# Load the first chunk synchronously, defer the rest via QTimer so the UI
# stays responsive on large documents. Tuned to roughly 80 KB of HTML.
_CHUNK_CHARS = 80_000


class DocumentPanel(QWidget):
    """Side‑by‑side compare panel.

    The panel is **always editable** so analysts can adjust the extracted
    text in place (fixing alignment / OCR slips) and then re‑compare. The
    diff highlighting is re‑rendered from the edited text on demand.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.browser = QTextEdit()
        self.browser.setReadOnly(False)
        self.browser.setAcceptRichText(False)   # typed text stays plain
        self.browser.setStyleSheet(_STYLE_VIEW)
        self.browser.setHtml(_PLACEHOLDER)
        layout.addWidget(self.browser)

        self._load_gen = 0   # incremented on every set_html(); stale deferred chunks bail out

    # -------------------------------------------------------------------
    def set_html(self, content: str):
        self.browser.setStyleSheet(_STYLE_VIEW)
        sb = self.browser.verticalScrollBar()
        saved_pos = sb.value()

        self._load_gen += 1
        gen = self._load_gen

        if len(content) <= _CHUNK_CHARS:
            self.browser.setHtml(
                f'<html><head>{_CSS}</head><body>{content}</body></html>'
            )
            sb.setValue(min(saved_pos, sb.maximum()))
            return

        # Load the first chunk now so the panel shows content immediately,
        # then schedule the remainder via zero-delay timers so Qt can process
        # paint/input events between chunks.
        split = content.rfind('</p>', 0, _CHUNK_CHARS + 500)
        split = (split + 4) if split >= 0 else _CHUNK_CHARS
        first, rest = content[:split], content[split:]

        self.browser.setHtml(
            f'<html><head>{_CSS}</head><body>{first}</body></html>'
        )
        sb.setValue(min(saved_pos, sb.maximum()))

        if rest:
            QTimer.singleShot(0, lambda: self._append_html(rest, gen))

    # -------------------------------------------------------------------
    def _append_html(self, fragment: str, gen: int):
        """Append one chunk of HTML at the document's end, then reschedule."""
        if gen != self._load_gen:
            return   # a newer set_html() was called; discard stale work

        if len(fragment) <= _CHUNK_CHARS:
            to_add, rest = fragment, ''
        else:
            split = fragment.rfind('</p>', 0, _CHUNK_CHARS + 500)
            if split >= 0:
                to_add, rest = fragment[:split + 4], fragment[split + 4:]
            else:
                to_add, rest = fragment, ''

        cur = self.browser.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertHtml(to_add)

        if rest:
            QTimer.singleShot(0, lambda: self._append_html(rest, gen))

    # -------------------------------------------------------------------
    def set_plain(self, text: str):
        """Load layout‑preserving plain text for direct editing."""
        self.browser.setStyleSheet(_STYLE_VIEW)
        self.browser.setPlainText(text)

    # -------------------------------------------------------------------
    def edited_text(self) -> str:
        """Visible text with non‑breaking spaces normalised back to spaces.

        Indentation rendered as ``&nbsp;`` in the diff view comes back as
        U+00A0; converting it lets the re‑extractor recover indent levels.
        """
        return self.browser.toPlainText().replace('\xa0', ' ')

    # -------------------------------------------------------------------
    def edited_document(self) -> Document:
        """Read the panel's current content back into a :class:`Document`,
        preserving per‑word emphasis (bold / italic / underline /
        strikethrough) and indentation so a Re‑Compare keeps formatting.

        Diff‑highlight backgrounds and the zero‑width navigation anchors are
        ignored — only genuine source emphasis is recovered.
        """
        doc = Document()
        qdoc = self.browser.document()
        block = qdoc.begin()
        while block.isValid():
            # Strip zero‑width anchors and normalise nbsp padding to spaces.
            raw = block.text().replace('​', '').replace('\xa0', ' ')
            if not raw.strip():
                doc.blocks.append(TextBlock(kind='blank'))
                block = block.next()
                continue

            indent = len(raw) - len(raw.lstrip(' '))
            spans: list[TextSpan] = []
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    ftext = frag.text().replace('​', '').replace('\xa0', ' ')
                    if ftext:
                        font = frag.charFormat().font()
                        spans.append(TextSpan(
                            text=ftext,
                            bold=font.bold(),
                            italic=font.italic(),
                            underline=font.underline(),
                            strikethrough=font.strikeOut(),
                        ))
                it += 1

            # Drop the leading indentation from the first span's text.
            if spans and indent:
                spans[0].text = spans[0].text.lstrip(' ')
            if spans:
                doc.blocks.append(TextBlock(spans=spans, indent=indent))
            else:
                doc.blocks.append(TextBlock(kind='blank'))
            block = block.next()

        while doc.blocks and doc.blocks[-1].is_blank():
            doc.blocks.pop()
        return doc

    # -------------------------------------------------------------------
    def scroll_to_anchor(self, anchor: str):
        if not anchor:
            return
        cursor = self._cursor_at_anchor(anchor)
        if cursor:
            self.browser.setTextCursor(cursor)
            self.browser.ensureCursorVisible()
            self._flash(cursor)

    # -------------------------------------------------------------------
    def _cursor_at_anchor(self, anchor: str):
        """
        Walk the document looking for a fragment whose format is an anchor
        and whose name matches ``anchor``.
        """
        doc = self.browser.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fmt = frag.charFormat()
                if fmt.isAnchor() and anchor in fmt.anchorNames():
                    c = self.browser.textCursor()
                    c.setPosition(frag.position())
                    return c
                it += 1
            block = block.next()
        return None

    # -------------------------------------------------------------------
    def _flash(self, cursor):
        sel = QTextEdit.ExtraSelection()
        flash_cursor = QTextCursor(cursor)
        flash_cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        sel.cursor = flash_cursor
        sel.format.setBackground(QColor('#fff3a0'))
        sel.format.setProperty(0x100000 + 1, True)      # FullWidthSelection
        self.browser.setExtraSelections([sel])
        QTimer.singleShot(1300, lambda: self.browser.setExtraSelections([]))

    # -------------------------------------------------------------------
    def clear(self):
        self.browser.setStyleSheet(_STYLE_VIEW)
        self.browser.setHtml(_PLACEHOLDER)

    # -------------------------------------------------------------------
    def scroll_fraction(self) -> float:
        sb = self.browser.verticalScrollBar()
        mx = sb.maximum()
        return sb.value() / mx if mx > 0 else 0.0

    # -------------------------------------------------------------------
    def set_scroll_fraction(self, frac: float):
        sb = self.browser.verticalScrollBar()
        if sb.maximum() > 0:
            sb.setValue(int(sb.maximum() * frac))