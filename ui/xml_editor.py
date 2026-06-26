# ui/xml_editor.py
import html as _html_mod
import re as _re
from lxml import etree  # type: ignore[attr-defined]

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QTextEdit, QTextBrowser, QSplitter,
    QPushButton, QLabel, QLineEdit, QCheckBox, QFrame,
    QListWidget, QListWidgetItem,
    QMessageBox, QInputDialog, QScrollArea, QDialog, QToolTip,
)
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QKeySequence, QShortcut, QTextCursor, QTextDocument, QPainter,
)
from PySide6.QtCore import QRegularExpression, Qt, QSize, QRect, QPoint, QTimer, QEvent


# -----------------------------------------------------------------------
# Live preview renderer
# -----------------------------------------------------------------------
_PREVIEW_CSS = """
<style>
  body {
    font-family: Arial, sans-serif;
    font-size: 13px;
    line-height: 1.7;
    color: #1e293b;
    background: #ffffff;
    padding: 16px 20px;
    margin: 0;
  }
  h1 { font-size: 18px; font-weight: bold; margin: 12px 0 4px; color: #0f172a; }
  h2 { font-size: 15px; font-weight: bold; margin: 8px 0 3px; color: #1e293b; }
  h3 { font-size: 13px; font-weight: bold; margin: 6px 0 2px; }
  p  { margin: 4px 0; }
  blockquote {
    margin: 4px 0 4px 14px;
    padding-left: 10px;
    border-left: 3px solid #cbd5e1;
    color: #475569;
    font-style: italic;
  }
  table { border-collapse: collapse; margin: 6px 0; width: 100%; }
  td, th { border: 1px solid #e2e8f0; padding: 4px 8px; }
  th { background: #f8fafc; font-weight: bold; }
  .innodrep {
    background: #fef3c7;
    border: 1px solid #f59e0b;
    border-radius: 3px;
    padding: 1px 4px;
  }
  .innodrep-badge {
    font-size: 9px;
    background: #d97706;
    color: #fff;
    border-radius: 2px;
    padding: 0 3px;
    margin-left: 3px;
    vertical-align: middle;
  }
  .inno-identifier {
    background: #e0f2fe;
    color: #0369a1;
    border-radius: 3px;
    padding: 0 5px;
    font-size: 11px;
    font-family: monospace;
  }
  .inno-ref {
    color: #6366f1;
    text-decoration: underline;
    cursor: pointer;
  }
  .fn-badge { color: #6366f1; font-size: 10px; vertical-align: super; }
  .meta-badge {
    background: #f1f5f9;
    color: #64748b;
    font-size: 10px;
    border-radius: 3px;
    padding: 0 4px;
    font-style: italic;
  }
  .inno-ref-block {
    border-bottom: 1px dashed #94a3b8;
    color: #334155;
  }
  .xml-error {
    background: #fef2f2;
    border: 1px solid #fca5a5;
    border-radius: 6px;
    padding: 12px 16px;
    color: #dc2626;
    font-family: monospace;
    font-size: 12px;
  }
  .preview-empty {
    color: #94a3b8;
    font-style: italic;
    text-align: center;
    margin-top: 40px;
  }
  .level-block { margin-left: 12px; }
</style>
"""

_PREVIEW_CSS_DARK = """
<style>
  body {
    font-family: Arial, sans-serif;
    font-size: 13px;
    line-height: 1.7;
    color: #cdd6f4;
    background: #1e1e2e;
    padding: 16px 20px;
    margin: 0;
  }
  h1 { font-size: 18px; font-weight: bold; margin: 12px 0 4px; color: #b4befe; }
  h2 { font-size: 15px; font-weight: bold; margin: 8px 0 3px; color: #cdd6f4; }
  h3 { font-size: 13px; font-weight: bold; margin: 6px 0 2px; }
  p  { margin: 4px 0; }
  blockquote {
    margin: 4px 0 4px 14px;
    padding-left: 10px;
    border-left: 3px solid #45475a;
    color: #a6adc8;
    font-style: italic;
  }
  table { border-collapse: collapse; margin: 6px 0; width: 100%; }
  td, th { border: 1px solid #313244; padding: 4px 8px; }
  th { background: #313244; font-weight: bold; }
  .innodrep {
    background: #3d2a00;
    border: 1px solid #d97706;
    border-radius: 3px;
    padding: 1px 4px;
  }
  .innodrep-badge {
    font-size: 9px;
    background: #b45309;
    color: #fef3c7;
    border-radius: 2px;
    padding: 0 3px;
    margin-left: 3px;
    vertical-align: middle;
  }
  .inno-identifier {
    background: #172554;
    color: #93c5fd;
    border-radius: 3px;
    padding: 0 5px;
    font-size: 11px;
    font-family: monospace;
  }
  .inno-ref {
    color: #a5b4fc;
    text-decoration: underline;
    cursor: pointer;
  }
  .fn-badge { color: #a5b4fc; font-size: 10px; vertical-align: super; }
  .meta-badge {
    background: #1e293b;
    color: #94a3b8;
    font-size: 10px;
    border-radius: 3px;
    padding: 0 4px;
    font-style: italic;
  }
  .inno-ref-block {
    border-bottom: 1px dashed #475569;
    color: #94a3b8;
  }
  .xml-error {
    background: #3d1a1a;
    border: 1px solid #f38ba8;
    border-radius: 6px;
    padding: 12px 16px;
    color: #f38ba8;
    font-family: monospace;
    font-size: 12px;
  }
  .preview-empty {
    color: #6c7086;
    font-style: italic;
    text-align: center;
    margin-top: 40px;
  }
  .level-block { margin-left: 12px; }
</style>
"""

# Tags whose content is passed through with no wrapping element
_TRANSPARENT_TAGS = frozenset({
    'body', 'root', 'document', 'doc', 'content', 'text', 'xml',
    'innodxml', 'innoddoc', 'article', 'chapter', 'part', 'book',
    # Structo string/reference wrappers — pass content through
    'innodstr', 'innodref', 'innoddoc',
    # Structo structural wrappers
    'innodtable', 'innodtr', 'innodtd',
    'thead', 'tbody', 'tfoot',
    # Generic containers
    'metadata', 'header', 'footer', 'main', 'section_group',
})


def _render_xml_preview(xml_text: str, dark: bool = False) -> str:
    """Convert XML source to styled HTML for the live preview pane.

    Renders all Structo-specific tags (innodLevel, innodHeading, innodReplace,
    inno-ref, innodFootnoteRef, innodImg, etc.) as clean document content —
    no raw tag names are shown to the user.
    """
    css = _PREVIEW_CSS_DARK if dark else _PREVIEW_CSS
    text = xml_text.strip()
    if not text:
        return (css +
                '<body><p class="preview-empty">Start typing XML to see a live preview.</p></body>')

    try:
        root = etree.fromstring(text.encode('utf-8'))
    except etree.XMLSyntaxError as e:
        short = str(e).split('\n')[0][:300]
        return (css +
                f'<body><div class="xml-error">'
                f'<b>XML syntax error</b><br>{_html_mod.escape(short)}'
                f'</div></body>')

    def _node(el) -> str:
        if not isinstance(el.tag, str):
            return _html_mod.escape(el.tail or '')

        local = el.tag.split('}')[-1].lower()
        inner = _html_mod.escape(el.text or '') + ''.join(_node(c) for c in el)
        tail  = _html_mod.escape(el.tail or '')

        # ── Common inline emphasis ─────────────────────────────────────────
        if local in ('b', 'strong', 'bold'):
            return f'<b>{inner}</b>{tail}'
        if local in ('i', 'em', 'italic'):
            return f'<em>{inner}</em>{tail}'
        if local == 'u':
            return f'<u>{inner}</u>{tail}'
        if local in ('s', 'del', 'strike', 'strikethrough', 'i-str'):
            return f'<s>{inner}</s>{tail}'
        if local == 'sup':
            return f'<sup>{inner}</sup>{tail}'
        if local == 'sub':
            return f'<sub>{inner}</sub>{tail}'
        if local in ('span', 'a', 'abbr', 'acronym', 'cite', 'code', 'kbd',
                     'samp', 'tt', 'var'):
            href = el.get('href', '')
            if href:
                return f'<span class="inno-ref" title="{_html_mod.escape(href)}">{inner}</span>{tail}'
            return f'{inner}{tail}'

        # ── Structo: innodReplace ──────────────────────────────────────────
        if local == 'innodreplace':
            # Nodes with no real inner content are paragraph/newline markers;
            # render them as a line break so the preview has correct spacing.
            if not inner.strip():
                return '<br>' + tail
            user_edit = el.get('userEdit') or el.get('useredit') or ''
            badge = ('<span class="innodrep-badge">edit</span>'
                     if user_edit else '')
            return f'<span class="innodrep">{inner}{badge}</span>{tail}'

        # ── Structo: innodHeading (section title) ──────────────────────────
        if local == 'innodheading':
            return f'<h2>{inner}</h2>{tail}'

        # ── Structo: innodLevel (section container) ────────────────────────
        if local == 'innodlevel':
            level = el.get('level', '1')
            margin = f'{int(level) * 8}px' if level.isdigit() else '8px'
            return f'<div style="margin-left:{margin}">{inner}</div>{tail}'

        # ── Structo: section ──────────────────────────────────────────────
        if local == 'section':
            level = el.get('level', '1')
            margin = f'{(int(level) - 1) * 12}px' if level.isdigit() else '0'
            return f'<div style="margin-left:{margin};margin-bottom:6px">{inner}</div>{tail}'

        # ── Structo: innodIdentifier ───────────────────────────────────────
        if local == 'innodidentifier':
            return f'<span class="inno-identifier">{inner}</span>{tail}'

        # ── Structo: inno-ref ──────────────────────────────────────────────
        if local == 'inno-ref':
            href = el.get('href', '')
            ref_type = el.get('type', 'ref')
            label = inner or _html_mod.escape(href)
            tip = f' title="{_html_mod.escape(href)} [{ref_type}]"' if href else ''
            return f'<span class="inno-ref"{tip}>{label}</span>{tail}'

        # ── Structo: innodFootnoteRef ──────────────────────────────────────
        if local == 'innodfootnoteref':
            fid = el.get('fid', '') or el.get('id', '')
            tip_text = el.get('text', inner)
            esc_tip = _html_mod.escape(tip_text)[:120] if tip_text else ''
            tip = f' title="{esc_tip}"' if esc_tip else ''
            return f'<sup><span class="fn-badge"{tip}>[{_html_mod.escape(fid) or "fn"}]</span></sup>{tail}'

        # ── Structo: innodFootnote ─────────────────────────────────────────
        if local in ('innodfootnote', 'footnoteref'):
            fid = el.get('fid', '') or el.get('id', '')
            return f'<sup><span class="fn-badge">[{_html_mod.escape(fid) or "fn"}]</span></sup>{tail}'

        # ── Structo: innodImg ──────────────────────────────────────────────
        if local == 'innodimg':
            src = el.get('src', '')
            # Prefer the child <img> src if present
            child_img = el.find('.//{http://www.w3.org/1999/xhtml}img')
            if child_img is None:
                child_img = el.find('.//img')
            if child_img is not None:
                src = child_img.get('src', src)
            if src:
                esc_src = _html_mod.escape(src)
                return (f'<img src="{esc_src}" alt="" '
                        f'style="max-width:100%;display:block;margin:4px 0;" />{tail}')
            return f'<span class="meta-badge">[img]</span>{tail}'

        # ── Structo: innodReference ────────────────────────────────────────
        if local == 'innodreference':
            return f'<span class="inno-ref-block">{inner}</span>{tail}'

        # ── Structo: innodMeta / innodTable wrappers ───────────────────────
        if local == 'innodmeta':
            name = el.get('name', 'meta')
            return f'<span class="meta-badge">[{_html_mod.escape(name)}]</span>{tail}'

        # ── Block elements ─────────────────────────────────────────────────
        if local in ('p', 'para', 'paragraph'):
            return f'<p>{inner}</p>{tail}'
        if local in ('heading', 'h'):
            return f'<h2>{inner}</h2>{tail}'
        if local == 'h1':
            return f'<h1>{inner}</h1>{tail}'
        if local == 'h2':
            return f'<h2>{inner}</h2>{tail}'
        if local in ('h3', 'h4', 'h5', 'h6'):
            return f'<h3>{inner}</h3>{tail}'
        if local == 'title':
            return f'<h3 style="margin:4px 0">{inner}</h3>{tail}'
        if local in ('li', 'item'):
            return f'<p style="padding-left:20px">• {inner}</p>{tail}'
        if local in ('ol', 'ul'):
            return f'<div style="padding-left:4px">{inner}</div>{tail}'
        if local == 'blockquote':
            return f'<blockquote>{inner}</blockquote>{tail}'
        if local in ('br', 'lb'):
            return f'<br>{tail}'
        if local in ('hr', 'rule'):
            return f'<hr style="border:none;border-top:1px solid #e2e8f0;margin:6px 0">{tail}'
        if local in ('pre', 'code'):
            return (f'<pre style="background:#f8fafc;padding:6px 10px;'
                    f'border-radius:4px;font-size:11px;overflow-x:auto">'
                    f'{inner}</pre>{tail}')

        # ── Table ──────────────────────────────────────────────────────────
        if local == 'table':
            return f'<table>{inner}</table>{tail}'
        if local == 'tr':
            return f'<tr>{inner}</tr>{tail}'
        if local == 'th':
            return f'<th>{inner}</th>{tail}'
        if local == 'td':
            return f'<td>{inner}</td>{tail}'

        # ── Footnote (generic) ─────────────────────────────────────────────
        if local in ('fn', 'footnote', 'note'):
            fn_text = inner.strip()[:80]
            tip = f' title="{_html_mod.escape(fn_text)}"' if fn_text else ''
            return f'<sup><span class="fn-badge"{tip}>[fn]</span></sup>{tail}'

        # ── Transparent wrappers ───────────────────────────────────────────
        if local in _TRANSPARENT_TAGS:
            return inner + tail

        # ── Unknown tag: pass content only (no badge, no tag leakage) ─────
        return inner + tail

    body_html = _node(root)
    if not body_html.strip():
        body_html = '<p class="preview-empty">Empty document.</p>'
    return f'{css}<body>{body_html}</body>'


# -----------------------------------------------------------------------
# Line-number gutter
# -----------------------------------------------------------------------
class _LineNumberArea(QWidget):
    def __init__(self, editor: '_CodeEdit'):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor._line_number_width(), 0)

    def paintEvent(self, event):
        self._editor._paint_line_numbers(event)


# -----------------------------------------------------------------------
# Code editor with line numbers, search highlights, matching-tag pairs
# -----------------------------------------------------------------------
class _CodeEdit(QPlainTextEdit):
    """Plain-text XML editor with line numbers, extra selections (search
    highlights + tag pair brackets), and auto-close-tag on '>'.
    """
    _OPEN_TAG_RE = _re.compile(r'<([A-Za-z_][\w:.-]*)(?:\s[^<>]*)?>$')

    def __init__(self):
        super().__init__()
        self._line_area = _LineNumberArea(self)
        self._err_lines: set[int] = set()
        self._search_sels: list = []
        self._tag_pair_sels: list = []
        self._dark = False

        # Debounced matching-tag update (heavy regex on large XML)
        self._tag_timer = QTimer(self)
        self._tag_timer.setSingleShot(True)
        self._tag_timer.setInterval(200)
        self._tag_timer.timeout.connect(self._do_tag_pair_update)

        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._on_cursor_changed)
        self._update_margin()

        # Autocomplete state
        self._ac_popup: '_XmlCompleter | None' = None
        self._ac_filter: str = ''

    # -------------------------------------------------------------------
    # Extra selection management (merges current-line, errors, search, tags)
    # -------------------------------------------------------------------
    def _on_cursor_changed(self):
        self._apply_extra_selections()
        self._tag_timer.start()

    def _apply_extra_selections(self):
        sels = []
        dark = self._dark

        # 1. Current-line highlight
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor('#313244' if dark else '#f1f5f9'))
            sel.format.setProperty(0x100000 + 1, True)   # FullWidthSelection
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            sels.append(sel)

        # 2. Error-line highlights
        for ln in self._err_lines:
            block = self.document().findBlockByNumber(ln)
            if block.isValid():
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(QColor('#4b1a1a' if dark else '#fee2e2'))
                sel.format.setProperty(0x100000 + 1, True)
                sel.cursor = QTextCursor(block)
                sels.append(sel)

        # 3. Search-match highlights (lower z-order than tag pair)
        sels.extend(self._search_sels)

        # 4. Matching-tag highlights (on top)
        sels.extend(self._tag_pair_sels)

        self.setExtraSelections(sels)

    def set_error_lines(self, lines: set):
        self._err_lines = lines
        self._apply_extra_selections()

    def set_search_selections(self, sels: list):
        self._search_sels = sels
        self._apply_extra_selections()

    # -------------------------------------------------------------------
    # Matching-tag highlight
    # -------------------------------------------------------------------
    def _do_tag_pair_update(self):
        self._tag_pair_sels = []
        text = self.toPlainText()
        pos  = self.textCursor().position()

        # Find a '<...>' region the cursor is inside OR immediately after.
        # Search backward up to 500 chars for the nearest '<'.
        lo     = max(0, pos - 500)
        lt_pos = text.rfind('<', lo, pos + 1)
        if lt_pos < 0:
            self._apply_extra_selections()
            return

        gt_pos = text.find('>', lt_pos)
        if gt_pos < 0:
            self._apply_extra_selections()
            return

        # Cursor must be within [lt_pos, gt_pos+1] — covers both inside the
        # tag AND immediately after the closing '>'.
        if not (lt_pos <= pos <= gt_pos + 1):
            self._apply_extra_selections()
            return

        tag_text    = text[lt_pos:gt_pos + 1]
        abs_lt      = lt_pos
        abs_tag_end = gt_pos + 1

        # Skip self-closing tags
        if tag_text.rstrip().endswith('/>'):
            self._apply_extra_selections()
            return

        m = _re.match(r'<(/?)([A-Za-z_][\w:.-]*)', tag_text)
        if not m:
            self._apply_extra_selections()
            return

        is_close = bool(m.group(1))
        tag_name = m.group(2)

        fmt = QTextCharFormat()
        fmt.setBackground(QColor('#7f1d1d' if self._dark else '#fca5a5'))

        def _sel(start: int, end: int) -> QTextEdit.ExtraSelection:
            s = QTextEdit.ExtraSelection()
            s.format = QTextCharFormat(fmt)
            c = self.textCursor()
            c.setPosition(start)
            c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            s.cursor = c
            return s

        self._tag_pair_sels.append(_sel(abs_lt, abs_tag_end))

        if is_close:
            mpos = self._find_matching_open(text, tag_name, abs_lt)
        else:
            mpos = self._find_matching_close(text, tag_name, abs_tag_end)

        if mpos >= 0:
            mend = text.find('>', mpos)
            if mend >= 0:
                self._tag_pair_sels.append(_sel(mpos, mend + 1))

        self._apply_extra_selections()

    def _find_matching_close(self, text: str, tag_name: str, after: int) -> int:
        depth = 1
        esc   = _re.escape(tag_name)
        pat   = _re.compile(rf'<({esc})(?:\s[^<>]*)?>|</{esc}>')
        for m in pat.finditer(text, after):
            if m.group().startswith('</'):
                depth -= 1
                if depth == 0:
                    return m.start()
            else:
                depth += 1
        return -1

    def _find_matching_open(self, text: str, tag_name: str, before: int) -> int:
        depth = 1
        esc   = _re.escape(tag_name)
        pat   = _re.compile(rf'<({esc})(?:\s[^<>]*)?>|</{esc}>')
        for m in reversed(list(pat.finditer(text, 0, before))):
            if m.group().startswith('</'):
                depth += 1
            else:
                depth -= 1
                if depth == 0:
                    return m.start()
        return -1

    # -------------------------------------------------------------------
    # Geometry helpers
    # -------------------------------------------------------------------
    def _line_number_width(self) -> int:
        digits = max(3, len(str(max(1, self.blockCount()))))
        return 10 + self.fontMetrics().horizontalAdvance('9') * digits

    def _update_margin(self, _=0):
        self.setViewportMargins(self._line_number_width(), 0, 0, 0)

    def _on_update_request(self, rect, dy):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(),
                                   self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(cr.left(), cr.top(),
                                    self._line_number_width(), cr.height())

    # -------------------------------------------------------------------
    # Line-number painting
    # -------------------------------------------------------------------
    def _paint_line_numbers(self, event):
        dark = self._dark
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor('#181825' if dark else '#f1f5f9'))
        painter.setFont(self.font())

        block  = self.firstVisibleBlock()
        num    = block.blockNumber()
        top    = round(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        bottom = top + round(self.blockBoundingRect(block).height())
        fh     = self.fontMetrics().height()
        w      = self._line_area.width()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                has_err = num in self._err_lines
                painter.setPen(QColor('#f38ba8' if has_err else ('#6c7086' if dark else '#94a3b8')))
                painter.drawText(
                    QRect(0, top, w - 5, fh),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    str(num + 1),
                )
            block  = block.next()
            top    = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            num   += 1
        painter.end()

    # -------------------------------------------------------------------
    # Autocomplete key handling
    # -------------------------------------------------------------------
    def keyPressEvent(self, event):
        key  = event.key()
        char = event.text()

        # ---- 1. Auto-close tag on '>' ----------------------------------------
        # Handled first so popup state never suppresses it.
        # The regex already rejects </tag> patterns (requires [A-Za-z_] after <),
        # so the only extra guard needed is to exclude self-closing />  tags.
        if char == '>':
            if self._ac_popup and self._ac_popup.isVisible():
                self._ac_popup.hide()
                self._ac_filter = ''
            cursor = self.textCursor()
            line_up_to = cursor.block().text()[:cursor.positionInBlock()] + '>'
            m = self._OPEN_TAG_RE.search(line_up_to)
            if m and not line_up_to.rstrip().endswith('/>'):
                tag   = m.group(1)
                close = f'</{tag}>'
                cursor.beginEditBlock()
                cursor.insertText('>' + close)
                cursor.setPosition(cursor.position() - len(close))
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return
            super().keyPressEvent(event)
            return

        # ---- 2. Show autocomplete on '<' -------------------------------------
        if char == '<':
            super().keyPressEvent(event)
            self._ac_filter = ''
            if self._ac_popup is None:
                self._ac_popup = _XmlCompleter(self)
                self._ac_popup.set_dark(self._dark)
            self._ac_popup.show_at_cursor('')
            return

        # ---- 3. Popup navigation when popup is visible ----------------------
        popup = self._ac_popup
        if popup is not None and popup.isVisible():
            if key == Qt.Key.Key_Escape:
                popup.hide(); self._ac_filter = ''; return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                tag = popup.selected_tag()
                if tag:
                    self._complete_tag(tag)
                else:
                    popup.hide(); self._ac_filter = ''
                    super().keyPressEvent(event)
                return
            if key == Qt.Key.Key_Down:
                popup.key_down(); return
            if key == Qt.Key.Key_Up:
                popup.key_up(); return
            if key == Qt.Key.Key_Backspace:
                super().keyPressEvent(event)
                if self._ac_filter:
                    self._ac_filter = self._ac_filter[:-1]
                    popup.update_filter(self._ac_filter)
                else:
                    popup.hide()
                return
            if char and (char.isalnum() or char in '-_:'):
                super().keyPressEvent(event)
                self._ac_filter += char
                popup.update_filter(self._ac_filter)
                return
            popup.hide(); self._ac_filter = ''

        # ---- 4. Default + autocomplete re-trigger ----------------------------
        super().keyPressEvent(event)
        # Re-open popup when typing inside a <tag_name context (handles the
        # case where the user dismissed the popup then kept typing letters).
        if char and (char.isalnum() or char in '-_:.'):
            self._try_reopen_popup()

    # -------------------------------------------------------------------
    # Autocomplete helpers
    # -------------------------------------------------------------------
    def _complete_tag(self, tag: str):
        """Replace the partial '<filter' with the tag snippet from the popup."""
        chars_to_remove = len(self._ac_filter) + 1
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.Left,
                         QTextCursor.MoveMode.KeepAnchor, chars_to_remove)

        snippet = self._ac_popup.get_snippet(tag) if self._ac_popup else None

        if snippet and '|' in snippet:
            idx    = snippet.index('|')
            before = snippet[:idx]
            after  = snippet[idx + 1:]
            cur.insertText(before + after)
            cur.setPosition(cur.position() - len(after))
            self.setTextCursor(cur)
        elif snippet:
            cur.insertText(snippet)
        else:
            close_tag = f'</{tag}>'
            cur.insertText(f'<{tag}>{close_tag}')
            cur.setPosition(cur.position() - len(close_tag))
            self.setTextCursor(cur)

        if self._ac_popup:
            self._ac_popup.hide()
        self._ac_filter = ''

    def trigger_autocomplete(self):
        if self._ac_popup is None:
            self._ac_popup = _XmlCompleter(self)
            self._ac_popup.set_dark(self._dark)
        self._ac_filter = ''
        self._ac_popup.show_at_cursor('')

    def _try_reopen_popup(self):
        """Show autocomplete when cursor is inside a <tag_name context.

        Called after every ordinary keystroke so the popup re-appears even
        if it was previously dismissed with Escape or hidden by a filter
        with no results.
        """
        cur  = self.textCursor()
        line = cur.block().text()[:cur.positionInBlock()]
        m    = _re.search(r'<([A-Za-z_][\w:.-]*)$', line)
        if not m:
            return
        tag_part = m.group(1)
        if self._ac_popup is None:
            self._ac_popup = _XmlCompleter(self)
            self._ac_popup.set_dark(self._dark)
        self._ac_filter = tag_part
        self._ac_popup.show_at_cursor(tag_part)

    # -------------------------------------------------------------------
    # Tooltip for error lines
    # -------------------------------------------------------------------
    def eventFilter(self, obj, event):
        if obj is self.viewport() and event.type() == QEvent.Type.ToolTip:
            cursor = self.cursorForPosition(event.pos())
            line   = cursor.blockNumber()
            if line in self._err_lines:
                parent = self.parent()
                msg = parent._val_bar._msg.text() if isinstance(parent, XmlEditor) else 'XML error'
                QToolTip.showText(event.globalPos(), msg, self)
            else:
                QToolTip.hideText()
            return True
        return super().eventFilter(obj, event)

    def set_dark(self, dark: bool):
        self._dark = dark
        if dark:
            self.setStyleSheet('background:#1e1e2e;color:#cdd6f4;border:none;padding:8px;')
        else:
            self.setStyleSheet('background:#ffffff;color:#1e293b;border:none;padding:8px;')
        self._apply_extra_selections()
        self._line_area.update()
        if self._ac_popup is not None:
            self._ac_popup.set_dark(dark)


# -----------------------------------------------------------------------
# Syntax highlighter
# -----------------------------------------------------------------------
class _XmlHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self._rules = self._make_rules(dark=False)

    @staticmethod
    def _make_rules(dark: bool) -> list:
        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:   f.setFontWeight(QFont.Weight.Bold)
            if italic: f.setFontItalic(True)
            return f

        if dark:
            return [
                (QRegularExpression(r'</?[\w:]+'),           fmt('#569cd6', bold=True)),
                (QRegularExpression(r'/?>'),                  fmt('#569cd6', bold=True)),
                (QRegularExpression(r'\b[\w:]+(?=\s*=)'),    fmt('#9cdcfe')),
                (QRegularExpression(r'"[^"]*"'),              fmt('#ce9178')),
                (QRegularExpression(r"'[^']*'"),              fmt('#ce9178')),
                (QRegularExpression(r'<!--.*?-->'),           fmt('#6a9955', italic=True)),
                (QRegularExpression(r'<!\[CDATA\[.*?\]\]>'), fmt('#569cd6')),
                (QRegularExpression(r'<\?.*?\?>'),            fmt('#c586c0')),
            ]
        return [
            (QRegularExpression(r'</?[\w:]+'),           fmt('#0451a5', bold=True)),
            (QRegularExpression(r'/?>'),                  fmt('#0451a5', bold=True)),
            (QRegularExpression(r'\b[\w:]+(?=\s*=)'),    fmt('#e50000')),
            (QRegularExpression(r'"[^"]*"'),              fmt('#a31515')),
            (QRegularExpression(r"'[^']*'"),              fmt('#a31515')),
            (QRegularExpression(r'<!--.*?-->'),           fmt('#008000', italic=True)),
            (QRegularExpression(r'<!\[CDATA\[.*?\]\]>'), fmt('#0451a5')),
            (QRegularExpression(r'<\?.*?\?>'),            fmt('#af00db')),
        ]

    def set_dark(self, dark: bool):
        self._rules = self._make_rules(dark)
        self.rehighlight()

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# -----------------------------------------------------------------------
# Validation bar
# -----------------------------------------------------------------------
class _ValidationBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(22)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(6)

        self._icon = QLabel('—')
        self._icon.setFixedWidth(14)
        self._msg  = QLabel('Open an XML file to begin editing.')
        f = QFont('Consolas', 10)
        self._msg.setFont(f)
        lay.addWidget(self._icon)
        lay.addWidget(self._msg, 1)
        self._dark = False
        self._cur_state = 'idle'
        self._cur_text  = 'Open an XML file to begin editing.'
        self._set_state('idle')

    def _set_state(self, state: str, text: str = ''):
        self._cur_state = state
        self._cur_text  = text
        if self._dark:
            colors = {
                'idle':  ('#6c7086', '#181825'),
                'ok':    ('#a6e3a1', '#1a3a2a'),
                'error': ('#f38ba8', '#3d1a1a'),
                'empty': ('#6c7086', '#181825'),
            }
            fg, bg = colors.get(state, ('#6c7086', '#181825'))
        else:
            colors = {
                'idle':  ('#94a3b8', '#f8fafc'),
                'ok':    ('#059669', '#f0fdf4'),
                'error': ('#dc2626', '#fef2f2'),
                'empty': ('#94a3b8', '#f8fafc'),
            }
            fg, bg = colors.get(state, ('#858585', '#f8fafc'))
        icons  = {'idle': '—', 'ok': '✓', 'error': '✕', 'empty': '—'}
        self.setStyleSheet(f'background:{bg};')
        self._icon.setStyleSheet(f'color:{fg};font-weight:bold;')
        self._icon.setText(icons.get(state, '—'))
        self._msg.setStyleSheet(f'color:{fg};font-size:11px;')
        self._msg.setText(text)

    def set_dark(self, dark: bool):
        self._dark = dark
        self._set_state(self._cur_state, self._cur_text)

    def set_idle(self):  self._set_state('idle', 'Open an XML file to begin editing.')
    def set_empty(self): self._set_state('empty', 'Empty document.')
    def set_valid(self): self._set_state('ok', 'Valid XML  ✓')

    def set_error(self, line: int, col: int, msg: str):
        short = msg.split('\n')[0][:120]
        self._set_state('error', f'Line {line}, Col {col}: {short}')


# -----------------------------------------------------------------------
# XML autocomplete popup  (light theme + attribute snippets)
# -----------------------------------------------------------------------
class _XmlCompleter(QFrame):
    """Floating tag-name autocomplete — child widget so it never steals focus."""

    ALL_TAGS = sorted([
        'b', 'blockquote', 'br', 'code', 'hr', 'i', 'li', 'ol', 'p', 'pre',
        's', 'section', 'table', 'td', 'th', 'title', 'tr', 'u', 'ul',
        'inno-ref', 'innodFootnote', 'innodFootnoteRef', 'innodHeading',
        'innodIdentifier', 'innodImg', 'innodLevel', 'innodMeta',
        'innodReference', 'innodReplace', 'innodTable', 'innodTd', 'innodTr',
    ])

    # Compact attribute hint shown next to each tag in the dropdown.
    # Keys must match ALL_TAGS exactly (case-sensitive).
    _TAG_ATTR_HINTS: dict = {
        'section':          'level="" id=""',
        'inno-ref':         'type="" href=""',
        'innodFootnote':    'fid="" id=""',
        'innodFootnoteRef': 'fid="" id="" text=""',
        'innodHeading':     '',
        'innodIdentifier':  '',
        'innodImg':         'src=""',
        'innodLevel':       'level=""',
        'innodMeta':        'name="" value=""',
        'innodReference':   '',
        'innodReplace':     'text=""',
        'innodTable':       '',
        'innodTd':          '',
        'innodTr':          '',
        'table':            '',
        'tr':               '',
        'td':               'colspan="" rowspan=""',
        'th':               'colspan="" rowspan=""',
    }

    # Insertion snippets with '|' marking the desired cursor position.
    # When a tag is selected from the popup, this snippet is inserted instead
    # of the bare <tag></tag>, providing attribute placeholders for required attrs.
    _TAG_SNIPPETS: dict = {
        'p':               '<p>|</p>',
        'b':               '<b>|</b>',
        'i':               '<i>|</i>',
        'u':               '<u>|</u>',
        's':               '<s>|</s>',
        'li':              '<li>|</li>',
        'ol':              '<ol>\n  <li>|</li>\n</ol>',
        'ul':              '<ul>\n  <li>|</li>\n</ul>',
        'blockquote':      '<blockquote>|</blockquote>',
        'pre':             '<pre>|</pre>',
        'code':            '<code>|</code>',
        'title':           '<title>|</title>',
        'table':           '<table>\n  <tr>\n    <th>|</th>\n  </tr>\n  <tr>\n    <td></td>\n  </tr>\n</table>',
        'tr':              '<tr>\n  <td>|</td>\n</tr>',
        'td':              '<td>|</td>',
        'th':              '<th>|</th>',
        'section':         '<section level="|" id=""></section>',
        'inno-ref':        '<inno-ref type="manual" href="|"></inno-ref>',
        'innodFootnote':   '<innodFootnote fid="|" id=""></innodFootnote>',
        'innodFootnoteRef':'<innodFootnoteRef fid="|" id="" text=""></innodFootnoteRef>',
        'innodHeading':    '<innodHeading>|</innodHeading>',
        'innodIdentifier': '<innodIdentifier>|</innodIdentifier>',
        'innodImg':        '<innodImg src="|">\n  <img src="" />\n</innodImg>',
        'innodLevel':      '<innodLevel level="|">\n  <section level="" id=""></section>\n</innodLevel>',
        'innodMeta':       '<innodMeta name="|" value=""></innodMeta>',
        'innodReference':  '<innodReference>|</innodReference>',
        'innodReplace':    '<innodReplace text="|"></innodReplace>',
        'innodTable':      '<innodTable>\n  <table>\n    <tr><td>|</td></tr>\n  </table>\n</innodTable>',
        'innodTd':         '<innodTd>\n  <td>|</td>\n</innodTd>',
        'innodTr':         '<innodTr>\n  <tr>|</tr>\n</innodTr>',
    }

    def __init__(self, editor: '_CodeEdit'):
        super().__init__(editor)
        self._editor = editor
        self.setStyleSheet(
            'QFrame{background:#ffffff;border:1px solid #cbd5e1;'
            'border-radius:5px;}'
        )
        self.setFixedWidth(400)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setStyleSheet(
            'QListWidget{background:#ffffff;color:#1e293b;border:none;'
            'font-family:Consolas,monospace;font-size:11px;}'
            'QListWidget::item{padding:3px 10px;color:#1e293b;}'
            'QListWidget::item:selected{background:#ede9fe;color:#4f46e5;}'
            'QListWidget::item:hover{background:#f1f5f9;}'
        )
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lay.addWidget(self._list)
        self.hide()

    def set_dark(self, dark: bool):
        if dark:
            self.setStyleSheet(
                'QFrame{background:#1e1e2e;border:1px solid #45475a;border-radius:5px;}'
            )
            self._list.setStyleSheet(
                'QListWidget{background:#1e1e2e;color:#cdd6f4;border:none;'
                'font-family:Consolas,monospace;font-size:11px;}'
                'QListWidget::item{padding:3px 10px;color:#cdd6f4;}'
                'QListWidget::item:selected{background:#313244;color:#cba6f7;}'
                'QListWidget::item:hover{background:#313244;}'
            )
        else:
            self.setStyleSheet(
                'QFrame{background:#ffffff;border:1px solid #cbd5e1;border-radius:5px;}'
            )
            self._list.setStyleSheet(
                'QListWidget{background:#ffffff;color:#1e293b;border:none;'
                'font-family:Consolas,monospace;font-size:11px;}'
                'QListWidget::item{padding:3px 10px;color:#1e293b;}'
                'QListWidget::item:selected{background:#ede9fe;color:#4f46e5;}'
                'QListWidget::item:hover{background:#f1f5f9;}'
            )

    def get_snippet(self, tag: str) -> str | None:
        return self._TAG_SNIPPETS.get(tag)

    def show_at_cursor(self, filter_text: str = ''):
        self._populate(filter_text)
        if self._list.count() == 0:
            self.hide(); return
        rect = self._editor.cursorRect()
        pt   = self._editor.viewport().mapTo(self._editor, rect.bottomLeft())
        x    = min(pt.x(), self._editor.width() - self.width() - 4)
        y    = pt.y() + 2
        if y + self.height() > self._editor.height() - 4:
            y = pt.y() - self.height() - rect.height() - 2
        self.move(max(0, x), max(0, y))
        self.show(); self.raise_()

    def update_filter(self, text: str):
        self._populate(text)
        if self._list.count() == 0:
            self.hide()
        elif not self.isVisible():
            self.show_at_cursor(text)

    def key_down(self):
        r = self._list.currentRow()
        if r < self._list.count() - 1:
            self._list.setCurrentRow(r + 1)

    def key_up(self):
        r = self._list.currentRow()
        if r > 0:
            self._list.setCurrentRow(r - 1)

    def selected_tag(self) -> str:
        item = self._list.currentItem()
        if not item:
            return ''
        return item.data(Qt.ItemDataRole.UserRole) or item.text()

    def _populate(self, filter_text: str):
        self._list.clear()
        fl      = filter_text.lower()
        prefix  = [t for t in self.ALL_TAGS if t.lower().startswith(fl)]
        contain = [t for t in self.ALL_TAGS
                   if fl and fl in t.lower() and not t.lower().startswith(fl)]
        ordered = (prefix + contain) if fl else self.ALL_TAGS
        for tag in ordered:
            # Build inline attribute hint: prefer explicit _TAG_ATTR_HINTS,
            # fall back to extracting attr names from the snippet.
            hint = self._TAG_ATTR_HINTS.get(tag)
            if hint is None:
                snippet = self._TAG_SNIPPETS.get(tag, '')
                attrs   = _re.findall(r'\b(\w[\w-]*)="', snippet)
                hint    = '  '.join(f'{a}=""' for a in attrs) if attrs else ''
            label = f'{tag:<22} {hint}' if hint else tag
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, tag)   # store real tag name
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        n     = min(self._list.count(), 10)
        row_h = self._list.sizeHintForRow(0) if self._list.count() > 0 else 22
        self.setFixedHeight(n * row_h + 2)


# -----------------------------------------------------------------------
# Inline Find / Replace bar  (VS Code-style)
# -----------------------------------------------------------------------
class _XmlSearchBar(QWidget):
    """Inline search bar with match highlighting, Prev/Next, and optional Replace."""

    _BTN_SS = (
        'QPushButton{background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;'
        'border-radius:3px;padding:2px 7px;font-size:11px;min-width:22px;}'
        'QPushButton:hover{background:#e2e8f0;color:#334155;}'
        'QPushButton:checked{background:#ede9fe;color:#4f46e5;border-color:#c4b5fd;}'
    )
    _INPUT_SS = (
        'QLineEdit{background:#ffffff;border:1px solid #cbd5e1;border-radius:3px;'
        'padding:2px 8px;font-size:11px;color:#1e293b;}'
        'QLineEdit:focus{border-color:#6366f1;outline:none;}'
    )

    def __init__(self, edit: '_CodeEdit', parent=None):
        super().__init__(parent)
        self._edit:    '_CodeEdit' = edit
        self._matches: list        = []   # list of (start, end)
        self._current: int         = -1

        self.setStyleSheet('background:#f8fafc;border-bottom:1px solid #e2e8f0;')

        # ── Find row ──────────────────────────────────────────────────────
        find_row = QHBoxLayout()
        find_row.setContentsMargins(8, 4, 8, 2)
        find_row.setSpacing(5)

        self._btn_expand = QPushButton('⇄')
        self._btn_expand.setCheckable(True)
        self._btn_expand.setToolTip('Toggle Replace')
        self._btn_expand.setStyleSheet(self._BTN_SS)
        self._btn_expand.setFixedWidth(26)

        self._input = QLineEdit()
        self._input.setPlaceholderText('Find in XML…')
        self._input.setFixedWidth(190)
        self._input.setStyleSheet(self._INPUT_SS)

        self._case_cb = QCheckBox('Aa')
        self._case_cb.setToolTip('Match case')
        self._case_cb.setStyleSheet(
            'QCheckBox{color:#475569;font-size:11px;spacing:3px;}'
            'QCheckBox::indicator{width:13px;height:13px;}'
        )

        self._count_lbl = QLabel('')
        self._count_lbl.setFixedWidth(76)
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._count_lbl.setStyleSheet('color:#64748b;font-size:11px;')

        self._btn_prev  = QPushButton('▲')
        self._btn_next  = QPushButton('▼')
        self._btn_close = QPushButton('✕')
        for b in (self._btn_prev, self._btn_next):
            b.setStyleSheet(self._BTN_SS)
            b.setFixedWidth(26)
        self._btn_close.setFixedWidth(22)
        self._btn_close.setStyleSheet(
            'QPushButton{background:transparent;color:#94a3b8;border:none;font-size:12px;}'
            'QPushButton:hover{color:#dc2626;}'
        )
        self._btn_prev.setToolTip('Previous match  Shift+Enter')
        self._btn_next.setToolTip('Next match  Enter')

        find_row.addWidget(self._btn_expand)
        find_row.addWidget(self._input)
        find_row.addWidget(self._case_cb)
        find_row.addWidget(self._count_lbl)
        find_row.addStretch()
        find_row.addWidget(self._btn_prev)
        find_row.addWidget(self._btn_next)
        find_row.addWidget(self._btn_close)

        # ── Replace row (hidden by default) ──────────────────────────────
        self._repl_widget = QWidget()
        self._repl_widget.setStyleSheet('background:transparent;')
        repl_row = QHBoxLayout(self._repl_widget)
        repl_row.setContentsMargins(8, 0, 8, 4)
        repl_row.setSpacing(5)
        repl_row.addSpacing(31)  # align with find input

        self._repl_input = QLineEdit()
        self._repl_input.setPlaceholderText('Replace with…')
        self._repl_input.setFixedWidth(190)
        self._repl_input.setStyleSheet(self._INPUT_SS)

        self._btn_repl_one = QPushButton('Replace')
        self._btn_repl_all = QPushButton('Replace All')
        for b in (self._btn_repl_one, self._btn_repl_all):
            b.setStyleSheet(self._BTN_SS)

        repl_row.addWidget(self._repl_input)
        repl_row.addWidget(self._btn_repl_one)
        repl_row.addWidget(self._btn_repl_all)
        repl_row.addStretch()

        self._repl_widget.setVisible(False)

        # ── Assembly ──────────────────────────────────────────────────────
        vlay = QVBoxLayout(self)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)
        vlay.addLayout(find_row)
        vlay.addWidget(self._repl_widget)
        self.setVisible(False)

        # ── Wiring ───────────────────────────────────────────────────────
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self.find_next)
        self._case_cb.toggled.connect(lambda _: self._on_text_changed(self._input.text()))
        self._btn_expand.toggled.connect(self._repl_widget.setVisible)
        self._btn_prev.clicked.connect(self.find_prev)
        self._btn_next.clicked.connect(self.find_next)
        self._btn_close.clicked.connect(self.close_bar)
        self._btn_repl_one.clicked.connect(self._replace_one)
        self._btn_repl_all.clicked.connect(self._replace_all)

        # Escape closes the bar
        esc = QShortcut(QKeySequence('Escape'), self)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(self.close_bar)

    # ── Public API ────────────────────────────────────────────────────────
    def open_find(self):
        self._btn_expand.setChecked(False)
        self._repl_widget.setVisible(False)
        self.setVisible(True)
        self._input.setFocus()
        self._input.selectAll()
        self._on_text_changed(self._input.text())

    def open_replace(self):
        self._btn_expand.setChecked(True)
        self._repl_widget.setVisible(True)
        self.setVisible(True)
        self._input.setFocus()
        self._input.selectAll()
        self._on_text_changed(self._input.text())

    def close_bar(self):
        self.setVisible(False)
        self._edit.set_search_selections([])
        self._matches = []
        self._current = -1
        self._edit.setFocus()

    def set_dark(self, dark: bool):
        if dark:
            btn_ss = (
                'QPushButton{background:#313244;color:#cdd6f4;border:1px solid #45475a;'
                'border-radius:3px;padding:2px 7px;font-size:11px;min-width:22px;}'
                'QPushButton:hover{background:#45475a;color:#cdd6f4;}'
                'QPushButton:checked{background:#4c1d95;color:#e9d5ff;border-color:#7c3aed;}'
            )
            input_ss = (
                'QLineEdit{background:#313244;border:1px solid #45475a;border-radius:3px;'
                'padding:2px 8px;font-size:11px;color:#cdd6f4;}'
                'QLineEdit:focus{border-color:#7c3aed;outline:none;}'
            )
            self.setStyleSheet('background:#181825;border-bottom:1px solid #313244;')
            self._repl_widget.setStyleSheet('background:transparent;')
            self._count_lbl.setStyleSheet('color:#6c7086;font-size:11px;')
        else:
            btn_ss = self._BTN_SS
            input_ss = self._INPUT_SS
            self.setStyleSheet('background:#f8fafc;border-bottom:1px solid #e2e8f0;')
            self._repl_widget.setStyleSheet('background:transparent;')
            self._count_lbl.setStyleSheet('color:#64748b;font-size:11px;')
        for b in (self._btn_expand, self._btn_prev, self._btn_next,
                  self._btn_repl_one, self._btn_repl_all):
            b.setStyleSheet(btn_ss)
        self._input.setStyleSheet(input_ss)
        self._repl_input.setStyleSheet(input_ss)

    # ── Search logic ──────────────────────────────────────────────────────
    def _on_text_changed(self, text: str):
        self._find_all(text)

    def _find_all(self, text: str):
        self._matches = []
        self._current = -1

        if not text:
            self._edit.set_search_selections([])
            self._count_lbl.setText('')
            return

        doc_text = self._edit.toPlainText()
        flags = 0 if self._case_cb.isChecked() else _re.IGNORECASE
        try:
            for m in _re.compile(_re.escape(text), flags).finditer(doc_text):
                self._matches.append((m.start(), m.end()))
        except _re.error:
            pass

        if self._matches:
            self._highlight_all()
            self.find_next()
        else:
            self._edit.set_search_selections([])
            self._count_lbl.setText('No results')
            self._count_lbl.setStyleSheet('color:#dc2626;font-size:11px;')

    def _highlight_all(self):
        fmt_inactive = QTextCharFormat()
        fmt_inactive.setBackground(QColor('#fef3c7'))

        fmt_active = QTextCharFormat()
        fmt_active.setBackground(QColor('#f59e0b'))
        fmt_active.setForeground(QColor('#ffffff'))

        sels = []
        for i, (start, end) in enumerate(self._matches):
            sel = QTextEdit.ExtraSelection()
            sel.format = QTextCharFormat(
                fmt_active if i == self._current else fmt_inactive
            )
            c = self._edit.textCursor()
            c.setPosition(start)
            c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            sels.append(sel)

        self._edit.set_search_selections(sels)

    def find_next(self):
        if not self._matches:
            return
        self._current = (self._current + 1) % len(self._matches)
        self._go_to_current()

    def find_prev(self):
        if not self._matches:
            return
        self._current = (self._current - 1) % len(self._matches)
        self._go_to_current()

    def _go_to_current(self):
        if not self._matches or self._current < 0:
            return
        start, end = self._matches[self._current]
        c = self._edit.textCursor()
        c.setPosition(start)
        c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self._edit.setTextCursor(c)
        self._edit.ensureCursorVisible()
        n = len(self._matches)
        self._count_lbl.setText(f'{self._current + 1} of {n}')
        self._count_lbl.setStyleSheet('color:#059669;font-size:11px;')
        self._highlight_all()

    def _replace_one(self):
        text = self._input.text()
        repl = self._repl_input.text()
        if not text or not self._matches:
            return
        cur = self._edit.textCursor()
        sel = cur.selectedText()
        cs  = self._case_cb.isChecked()
        if sel and ((sel == text) if cs else sel.lower() == text.lower()):
            cur.insertText(repl)
        self.find_next()

    def _replace_all(self):
        text = self._input.text()
        repl = self._repl_input.text()
        if not text:
            return
        content = self._edit.toPlainText()
        flags = 0 if self._case_cb.isChecked() else _re.IGNORECASE
        try:
            pat   = _re.compile(_re.escape(text), flags)
            count = len(pat.findall(content))
            new_c = pat.sub(repl, content)
        except _re.error:
            return
        if count:
            self._edit.setPlainText(new_c)
            self._count_lbl.setText(f'Replaced {count}')
            self._count_lbl.setStyleSheet('color:#059669;font-size:11px;')


# -----------------------------------------------------------------------
# Shortcuts reference dialog
# -----------------------------------------------------------------------
class _ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('XML Editor — Keyboard Shortcuts')
        self.setModal(True)
        self.resize(520, 490)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        def _section(title: str, rows: list) -> str:
            header = (f'<tr><td colspan="2" style="padding:8px 4px 2px;'
                      f'color:#6366f1;font-weight:bold;font-size:12px">{title}</td></tr>')
            cells = ''.join(
                f'<tr>'
                f'<td style="padding:2px 12px 2px 4px;color:#0451a5;font-family:monospace;'
                f'white-space:nowrap">{k}</td>'
                f'<td style="padding:2px 4px;color:#334155">{v}</td>'
                f'</tr>'
                for k, v in rows
            )
            return header + cells

        html = '<table style="font-size:12px;border-collapse:collapse;width:100%">'
        html += _section('General', [
            ('Ctrl+S',       'Format XML and Save'),
            ('Ctrl+Shift+F', 'Format XML (pretty-print only)'),
            ('Ctrl+Shift+E', 'Wrap selection with &lt;innodReplace userEdit&gt;'),
            ('Ctrl+Z',       'Undo'),
            ('Ctrl+Y',       'Redo'),
            ('Ctrl+F',       'Find in XML (inline bar)'),
            ('Ctrl+H',       'Find &amp; Replace (inline bar)'),
            ('Ctrl+G',       'Go to Line'),
            ('Ctrl+/',       'Toggle XML comment'),
            ('F1',           'Show this shortcuts reference'),
        ])
        html += _section('Emphasis (inline tags)', [
            ('Alt+B', 'Wrap selection with &lt;b&gt; (Bold)'),
            ('Alt+I', 'Wrap selection with &lt;i&gt; (Italic)'),
            ('Alt+U', 'Wrap selection with &lt;u&gt; (Underline)'),
            ('Alt+S', 'Wrap selection with &lt;s&gt; (Strikethrough)'),
        ])
        html += _section('Structo structure templates', [
            ('Alt+P',      'Insert &lt;innodReplace&gt; + &lt;p&gt; paragraph'),
            ('Alt+L',      'Insert full &lt;innodLevel&gt; / &lt;section&gt; template'),
            ('Alt+Q',      'Insert &lt;innodIdentifier&gt;'),
            ('Alt+H',      'Insert &lt;innodHeading&gt;'),
            ('Alt+F',      'Insert &lt;innodFootnoteRef&gt; template'),
            ('Alt+M',      'Insert &lt;innodImg&gt; template'),
            ('Alt+6',      'Insert 4-column &lt;innodTable&gt; template'),
            ('Alt+7',      'Insert &lt;inno-ref type="manual"&gt;'),
            ('Ctrl+Space', 'Show XML tag autocomplete popup'),
        ])
        html += _section('Navigation', [
            ('Ctrl+F',       'Open inline Find bar'),
            ('Enter',        'Next match (in Find bar)'),
            ('Shift+Enter',  'Previous match (in Find bar)'),
            ('Escape',       'Close Find bar'),
        ])
        html += '</table>'

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('QScrollArea{border:none;}')
        inner = QLabel(html)
        inner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner.setWordWrap(True)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


# -----------------------------------------------------------------------
# Public XmlEditor widget
# -----------------------------------------------------------------------
class XmlEditor(QWidget):
    """XML editor with syntax highlighting, line numbers, live validation,
    inline find/replace, matching-tag navigation, and live preview."""

    _TBTN_LIGHT = (
        'QPushButton{background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;'
        'padding:3px 10px;border-radius:3px;font-size:11px;}'
        'QPushButton:hover{background:#e2e8f0;color:#334155;}'
        'QPushButton:checked{background:#ede9fe;color:#5b21b6;border-color:#c4b5fd;}'
    )
    _TBTN_DARK = (
        'QPushButton{background:#313244;color:#cdd6f4;border:1px solid #45475a;'
        'padding:3px 10px;border-radius:3px;font-size:11px;}'
        'QPushButton:hover{background:#45475a;color:#cdd6f4;}'
        'QPushButton:checked{background:#4c1d95;color:#e9d5ff;border-color:#7c3aed;}'
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark_mode = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────────
        self._toolbar = QWidget()
        self._toolbar.setStyleSheet('background:#f8fafc;border-bottom:1px solid #e2e8f0;')
        tb = QHBoxLayout(self._toolbar)
        tb.setContentsMargins(6, 3, 6, 3)
        tb.setSpacing(4)

        def _tbtn(label: str, tip: str, checkable: bool = False) -> QPushButton:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.setStyleSheet(self._TBTN_LIGHT)
            return b

        self._btn_fmt     = _tbtn('Format XML',     'Pretty-print XML (Ctrl+Shift+F)')
        self._btn_find    = _tbtn('Find',            'Find in XML (Ctrl+F)')
        self._btn_repl    = _tbtn('Replace',         'Find & Replace (Ctrl+H)')
        self._btn_goto    = _tbtn('Go to Line',      'Jump to line number (Ctrl+G)')
        self._btn_cmt     = _tbtn('Comment',         'Toggle XML comment (Ctrl+/)')
        self._btn_undo    = _tbtn('↩ Undo',   'Ctrl+Z')
        self._btn_redo    = _tbtn('↪ Redo',   'Ctrl+Y')
        self._btn_preview = _tbtn('□ Preview', 'Toggle live preview (Ctrl+P)', checkable=True)
        self._btn_theme   = _tbtn('🌙 Dark',   'Switch to dark mode', checkable=True)
        self._btn_help    = _tbtn('⌨ Shortcuts', 'Keyboard shortcuts (F1)')

        self._toolbar_btns = [
            self._btn_fmt, self._btn_find, self._btn_repl,
            self._btn_goto, self._btn_cmt, self._btn_undo,
            self._btn_redo, self._btn_preview, self._btn_theme, self._btn_help,
        ]

        for btn in (self._btn_fmt, self._btn_find, self._btn_repl,
                    self._btn_goto, self._btn_cmt,
                    self._btn_undo, self._btn_redo, self._btn_preview,
                    self._btn_theme):
            tb.addWidget(btn)
        tb.addStretch()
        tb.addWidget(self._btn_help)
        root.addWidget(self._toolbar)

        # ── Inline Find / Replace bar ─────────────────────────────────────
        # Created before the editor so _search_bar can hold a reference to _edit
        self._edit = _CodeEdit()
        mono = QFont('Consolas', 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._edit.setFont(mono)
        self._edit.setStyleSheet(
            'background:#ffffff;color:#1e293b;border:none;padding:8px;'
        )
        self._edit.setPlaceholderText('Open an XML file to edit…')
        self._edit.setTabStopDistance(28)
        self._highlighter = _XmlHighlighter(self._edit.document())

        self._search_bar = _XmlSearchBar(self._edit, self)
        root.addWidget(self._search_bar)

        # ── Editor + Preview splitter ─────────────────────────────────────
        self._body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._body_splitter.setHandleWidth(4)
        self._body_splitter.addWidget(self._edit)

        self._preview = QTextBrowser()
        self._preview.setOpenLinks(False)
        self._preview.setStyleSheet(
            'background:#ffffff;border:none;border-left:1px solid #e2e8f0;'
        )
        self._preview.setHtml(
            _PREVIEW_CSS +
            '<body><p class="preview-empty">'
            'Click <b>□ Preview</b> in the toolbar to see a live rendered view.'
            '</p></body>'
        )
        self._preview.setVisible(False)
        self._body_splitter.addWidget(self._preview)
        self._body_splitter.setSizes([600, 500])
        root.addWidget(self._body_splitter, 1)

        # Install tooltip event filter
        self._edit.viewport().installEventFilter(self._edit)

        # ── Validation bar ────────────────────────────────────────────────
        self._val_bar = _ValidationBar()
        root.addWidget(self._val_bar)

        # ── Timers ───────────────────────────────────────────────────────
        self._val_timer = QTimer(self)
        self._val_timer.setSingleShot(True)
        self._val_timer.setInterval(800)
        self._val_timer.timeout.connect(self._run_validation)
        self._edit.document().contentsChanged.connect(self._val_timer.start)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(600)
        self._preview_timer.timeout.connect(self._update_preview)
        self._edit.document().contentsChanged.connect(self._on_content_for_preview)

        # ── Preview scroll sync ───────────────────────────────────────────
        self._edit.verticalScrollBar().valueChanged.connect(self._sync_preview_scroll)

        # ── Toolbar wiring ────────────────────────────────────────────────
        self._btn_fmt.clicked.connect(self._format_xml)
        self._btn_find.clicked.connect(self._search_bar.open_find)
        self._btn_repl.clicked.connect(self._search_bar.open_replace)
        self._btn_goto.clicked.connect(self._goto_line)
        self._btn_cmt.clicked.connect(self._toggle_comment)
        self._btn_undo.clicked.connect(self._edit.undo)
        self._btn_redo.clicked.connect(self._edit.redo)
        self._btn_preview.clicked.connect(self._toggle_preview)
        self._btn_theme.clicked.connect(self._toggle_theme)
        self._btn_help.clicked.connect(self._show_shortcuts)

        # ── Keyboard shortcuts ────────────────────────────────────────────
        QShortcut(QKeySequence('Ctrl+Shift+F'), self).activated.connect(self._format_xml)
        QShortcut(QKeySequence('Ctrl+F'),       self).activated.connect(self._search_bar.open_find)
        QShortcut(QKeySequence('Ctrl+H'),       self).activated.connect(self._search_bar.open_replace)
        QShortcut(QKeySequence('Ctrl+G'),       self).activated.connect(self._goto_line)
        QShortcut(QKeySequence('Ctrl+/'),       self).activated.connect(self._toggle_comment)
        QShortcut(QKeySequence('F1'),           self).activated.connect(self._show_shortcuts)
        QShortcut(QKeySequence('Ctrl+P'),       self).activated.connect(self._toggle_preview)

        # Emphasis wrapping
        QShortcut(QKeySequence('Alt+B'), self).activated.connect(lambda: self._wrap_with_tag('b'))
        QShortcut(QKeySequence('Alt+I'), self).activated.connect(lambda: self._wrap_with_tag('i'))
        QShortcut(QKeySequence('Alt+U'), self).activated.connect(lambda: self._wrap_with_tag('u'))
        QShortcut(QKeySequence('Alt+S'), self).activated.connect(lambda: self._wrap_with_tag('s'))

        QShortcut(QKeySequence('Ctrl+Shift+E'), self).activated.connect(
            lambda: self._wrap_with_tag('innodReplace', 'userEdit="true"', multiline=True))

        # Structo structure templates
        QShortcut(QKeySequence('Alt+P'), self).activated.connect(self._tpl_paragraph)
        QShortcut(QKeySequence('Alt+L'), self).activated.connect(self._tpl_level)
        QShortcut(QKeySequence('Alt+Q'), self).activated.connect(self._tpl_identifier)
        QShortcut(QKeySequence('Alt+H'), self).activated.connect(self._tpl_heading)
        QShortcut(QKeySequence('Alt+F'), self).activated.connect(self._tpl_footnote_ref)
        QShortcut(QKeySequence('Alt+M'), self).activated.connect(self._tpl_image)
        QShortcut(QKeySequence('Alt+6'), self).activated.connect(self._tpl_table)
        QShortcut(QKeySequence('Alt+7'), self).activated.connect(self._tpl_manual_ref)

        QShortcut(QKeySequence('Ctrl+Space'), self).activated.connect(
            self._edit.trigger_autocomplete)

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------
    def toPlainText(self) -> str:
        return self._edit.toPlainText()

    def setPlainText(self, text: str):
        self._edit.setPlainText(text)
        self._val_timer.start()

    def document(self):
        return self._edit.document()

    # -------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------
    def _run_validation(self):
        text = self._edit.toPlainText().strip()
        if not text:
            self._val_bar.set_empty()
            self._edit.set_error_lines(set())
            return
        try:
            etree.fromstring(text.encode('utf-8'))
            self._val_bar.set_valid()
            self._edit.set_error_lines(set())
        except etree.XMLSyntaxError as e:
            line = (e.lineno or 1) - 1
            col  = e.offset or 1
            self._val_bar.set_error(line + 1, col, str(e))
            self._edit.set_error_lines({line})

    # -------------------------------------------------------------------
    # Toolbar actions
    # -------------------------------------------------------------------
    def _format_xml(self):
        txt = self._edit.toPlainText().strip()
        if not txt:
            return
        try:
            tree   = etree.fromstring(txt.encode('utf-8'))
            pretty = etree.tostring(tree, pretty_print=True, encoding='unicode')
            self._edit.setPlainText(pretty)
        except etree.XMLSyntaxError as e:
            QMessageBox.warning(self, 'Format Error', f'Cannot format — invalid XML:\n{e}')

    def _goto_line(self):
        total = self._edit.document().blockCount()
        line, ok = QInputDialog.getInt(
            self, 'Go to Line', f'Line number (1–{total}):',
            value=self._edit.textCursor().blockNumber() + 1,
            minValue=1, maxValue=total
        )
        if ok:
            block = self._edit.document().findBlockByNumber(line - 1)
            cur   = self._edit.textCursor()
            cur.setPosition(block.position())
            self._edit.setTextCursor(cur)
            self._edit.ensureCursorVisible()
            self._edit.centerCursor()

    def _toggle_comment(self):
        cur = self._edit.textCursor()
        if cur.hasSelection():
            start, end = cur.selectionStart(), cur.selectionEnd()
        else:
            block = cur.block()
            start = block.position()
            end   = block.position() + block.length() - 1

        sel_cur = self._edit.textCursor()
        sel_cur.setPosition(start)
        sel_cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        txt      = sel_cur.selectedText()
        stripped = txt.strip()

        sel_cur.beginEditBlock()
        if stripped.startswith('<!--') and stripped.endswith('-->'):
            sel_cur.insertText(stripped[4:-3].strip())
        else:
            sel_cur.insertText(f'<!-- {txt.strip()} -->')
        sel_cur.endEditBlock()

    def _show_shortcuts(self):
        _ShortcutsDialog(self).exec()

    # -------------------------------------------------------------------
    # Tag wrapping
    # -------------------------------------------------------------------
    def _wrap_with_tag(self, tag: str, attrs: str = '', multiline: bool = False):
        cur       = self._edit.textCursor()
        open_tag  = '<' + tag + ((' ' + attrs) if attrs else '') + '>'
        close_tag = '</' + tag + '>'
        indent = ''
        if multiline:
            sp       = min(cur.anchor(), cur.position()) if cur.hasSelection() else cur.position()
            raw_line = self._edit.document().findBlock(sp).text()
            indent   = raw_line[:len(raw_line) - len(raw_line.lstrip(' \t'))]
        cur.beginEditBlock()
        if cur.hasSelection():
            start    = min(cur.anchor(), cur.position())
            end      = max(cur.anchor(), cur.position())
            selected = self._edit.toPlainText()[start:end]
            if multiline:
                cur.insertText(open_tag + '\n' + indent + '    ' + selected + '\n' + indent + close_tag)
            else:
                cur.insertText(open_tag + selected + close_tag)
            cur.endEditBlock()
        else:
            if multiline:
                cur.insertText(open_tag + '\n' + indent + '    \n' + indent + close_tag)
                end_pos = cur.position() - len('\n' + indent + close_tag)
            else:
                cur.insertText(open_tag + close_tag)
                end_pos = cur.position() - len(close_tag)
            cur.endEditBlock()
            cur.setPosition(end_pos)
            self._edit.setTextCursor(cur)

    # -------------------------------------------------------------------
    # Template insertion
    # -------------------------------------------------------------------
    def _insert_template(self, template: str):
        if '|' in template:
            idx    = template.index('|')
            before = template[:idx]
            after  = template[idx + 1:]
            text   = before + after
            offset = len(after)
        else:
            text   = template
            offset = 0
        cur = self._edit.textCursor()
        cur.beginEditBlock()
        cur.insertText(text)
        if offset:
            cur.setPosition(cur.position() - offset)
            self._edit.setTextCursor(cur)
        cur.endEditBlock()

    def _tpl_paragraph(self):
        self._insert_template(
            '<innodReplace text="&#10;&#10;">\n'
            '               </innodReplace><p>|</p>'
        )

    def _tpl_level(self):
        self._insert_template(
            '<innodReplace>\n'
            '</innodReplace>\n'
            '<innodLevel level="">\n'
            '  <section level="">\n'
            '    <innodReplace>\n'
            '    </innodReplace>\n'
            '    <innodHeading>\n'
            '      <title>|</title>\n'
            '    </innodHeading>\n'
            '    <innodReplace text=" ">\n'
            '    </innodReplace>\n'
            '    <p></p>\n'
            '    <innodReplace>\n'
            '    </innodReplace>\n'
            '  </section>\n'
            '</innodLevel>'
        )

    def _tpl_identifier(self):
        self._insert_template('<innodIdentifier>|</innodIdentifier>')

    def _tpl_heading(self):
        self._insert_template('<innodHeading>|</innodHeading>')

    def _tpl_footnote_ref(self):
        self._insert_template(
            '<innodFootnoteRef fid="|" id="" text="">\n'
            '    <footnoteref fid=""></footnoteref>\n'
            '</innodFootnoteRef>'
        )

    def _tpl_image(self):
        self._insert_template(
            '<innodReplace>\n'
            '</innodReplace>\n'
            '<innodImg src="/Images/innodDOCid/img-1.png">\n'
            '    <img src="images/img-1.png" />\n'
            '</innodImg>|'
        )

    def _tpl_table(self):
        self._insert_template(
            '<innodTable><table>\n'
            '<innodTr><tr>\n'
            '<innodTd><th>\n'
            '<p>|</p>\n'
            '</th></innodTd>\n'
            '<innodTd><th>\n'
            '<p></p>\n'
            '</th></innodTd>\n'
            '<innodTd><th>\n'
            '<p></p>\n'
            '</th></innodTd>\n'
            '<innodTd><th>\n'
            '<p></p>\n'
            '</th></innodTd>\n'
            '</tr></innodTr>\n'
            '<innodTr><tr>\n'
            '<innodTd><td>\n'
            '<p></p>\n'
            '</td></innodTd>\n'
            '<innodTd><td>\n'
            '<p></p>\n'
            '</td></innodTd>\n'
            '<innodTd><td>\n'
            '<p></p>\n'
            '</td></innodTd>\n'
            '<innodTd><td>\n'
            '<p></p>\n'
            '</td></innodTd>\n'
            '</tr></innodTr>\n'
            '</table></innodTable>'
        )

    def _tpl_manual_ref(self):
        self._insert_template('<inno-ref type="manual" href="/us/irc/">|</inno-ref>')

    # -------------------------------------------------------------------
    # Public API: format (called by MainWindow Ctrl+S)
    # -------------------------------------------------------------------
    def format_xml(self):
        self._format_xml()

    # -------------------------------------------------------------------
    # Theme toggle
    # -------------------------------------------------------------------
    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        dark = self._dark_mode

        if dark:
            self._toolbar.setStyleSheet('background:#181825;border-bottom:1px solid #313244;')
            self._preview.setStyleSheet(
                'background:#1e1e2e;border:none;border-left:1px solid #313244;'
            )
            self._btn_theme.setText('☀ Light')
            self._btn_theme.setToolTip('Switch to light mode')
        else:
            self._toolbar.setStyleSheet('background:#f8fafc;border-bottom:1px solid #e2e8f0;')
            self._preview.setStyleSheet(
                'background:#ffffff;border:none;border-left:1px solid #e2e8f0;'
            )
            self._btn_theme.setText('🌙 Dark')
            self._btn_theme.setToolTip('Switch to dark mode')

        tbtn_ss = self._TBTN_DARK if dark else self._TBTN_LIGHT
        for btn in self._toolbar_btns:
            btn.setStyleSheet(tbtn_ss)

        self._edit.set_dark(dark)
        self._highlighter.set_dark(dark)
        self._val_bar.set_dark(dark)
        self._search_bar.set_dark(dark)

        if self._preview.isVisible():
            self._update_preview()

    # -------------------------------------------------------------------
    # Live preview
    # -------------------------------------------------------------------
    def _toggle_preview(self):
        visible = not self._preview.isVisible()
        self._preview.setVisible(visible)
        self._btn_preview.setChecked(visible)
        self._btn_preview.setText('■ Preview' if visible else '□ Preview')
        if visible:
            self._update_preview()

    def _on_content_for_preview(self):
        if self._preview.isVisible():
            self._preview_timer.start()

    def _update_preview(self):
        if not self._preview.isVisible():
            return
        xml_text = self._edit.toPlainText()
        html     = _render_xml_preview(xml_text, dark=self._dark_mode)
        sb       = self._preview.verticalScrollBar()
        old_val  = sb.value()
        self._preview.setHtml(html)
        QTimer.singleShot(0, lambda: sb.setValue(min(old_val, sb.maximum())))

    def _sync_preview_scroll(self, value: int):
        """Mirror editor scroll position proportionally in the preview pane."""
        if not self._preview.isVisible():
            return
        edit_sb    = self._edit.verticalScrollBar()
        preview_sb = self._preview.verticalScrollBar()
        if edit_sb.maximum() > 0:
            frac = value / edit_sb.maximum()
            preview_sb.setValue(int(frac * preview_sb.maximum()))
