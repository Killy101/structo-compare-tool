import re as _re
from lxml import etree

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPlainTextEdit, QTextEdit,
    QPushButton, QDialog, QLabel, QLineEdit, QCheckBox,
    QMessageBox, QInputDialog, QScrollArea,
)
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QKeySequence, QShortcut, QTextCursor, QTextDocument, QPainter,
)
from PySide6.QtCore import QRegularExpression, Qt, QSize, QRect, QTimer


# ── Line-number gutter ────────────────────────────────────────────────────────

class _LineNumberArea(QWidget):
    def __init__(self, editor: '_CodeEdit'):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor._line_number_width(), 0)

    def paintEvent(self, event):
        self._editor._paint_line_numbers(event)


# ── Code editor (QPlainTextEdit + line numbers + auto-close tags) ─────────────

class _CodeEdit(QPlainTextEdit):
    """Plain-text editor with XML auto-close-tag behaviour and line numbers."""

    _OPEN_TAG_RE = _re.compile(r'<([A-Za-z_][\w:.-]*)(?:\s[^<>]*)?>$')

    def __init__(self):
        super().__init__()
        self._line_area = _LineNumberArea(self)
        self._err_lines: set = set()   # 0-based block numbers with validation errors

        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._repaint_current_line)
        self._update_margin()

    # ── Line number geometry ──────────────────────────────────────────────────

    def _line_number_width(self) -> int:
        digits = max(3, len(str(max(1, self.blockCount()))))
        return 10 + self.fontMetrics().horizontalAdvance('9') * digits

    def _update_margin(self, _=0):
        self.setViewportMargins(self._line_number_width(), 0, 0, 0)

    def _on_update_request(self, rect, dy):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(cr.left(), cr.top(),
                                    self._line_number_width(), cr.height())

    # ── Line number painting ──────────────────────────────────────────────────

    def _paint_line_numbers(self, event):
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor('#f1f5f9'))
        painter.setFont(self.font())

        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = round(
            self.blockBoundingGeometry(block)
                .translated(self.contentOffset()).top()
        )
        bottom = top + round(self.blockBoundingRect(block).height())
        fh = self.fontMetrics().height()
        w  = self._line_area.width()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                has_err = num in self._err_lines
                painter.setPen(QColor('#dc2626') if has_err else QColor('#94a3b8'))
                painter.drawText(
                    QRect(0, top, w - 5, fh),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    str(num + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            num += 1
        painter.end()

    # ── Current-line highlight + error-line highlight ─────────────────────────

    def _repaint_current_line(self):
        selections = []

        # Current line — subtle highlight
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor('#f1f5f9'))
            sel.format.setProperty(0x100000 + 1, True)   # FullWidthSelection
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            selections.append(sel)

        # Error lines — red background
        for line_num in self._err_lines:
            block = self.document().findBlockByLineNumber(line_num)
            if block.isValid():
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(QColor('#fee2e2'))
                sel.format.setProperty(0x100000 + 1, True)
                c = QTextCursor(block)
                sel.cursor = c
                selections.append(sel)

        self.setExtraSelections(selections)

    def set_error_lines(self, lines: set):
        self._err_lines = lines
        self._repaint_current_line()

    # ── Auto-close tag on '>' ─────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.text() == '>':
            cursor = self.textCursor()
            line_start = cursor.block().position()
            prefix = self.toPlainText()[line_start:cursor.position()]
            super().keyPressEvent(event)
            candidate = prefix + '>'
            m = self._OPEN_TAG_RE.search(candidate)
            if m and not candidate.rstrip().endswith('/>') \
                    and not candidate.lstrip().startswith('</'):
                tag = m.group(1)
                c = self.textCursor()
                c.insertText(f'</{tag}>')
                c.movePosition(QTextCursor.MoveOperation.Left,
                               QTextCursor.MoveMode.MoveAnchor, len(tag) + 3)
                self.setTextCursor(c)
            return
        super().keyPressEvent(event)


# ── XML syntax highlighter ────────────────────────────────────────────────────

class _XmlHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)

        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            if italic:
                f.setFontItalic(True)
            return f

        self._rules = [
            (QRegularExpression(r'</?[\w:]+'),        fmt('#0451a5', bold=True)),
            (QRegularExpression(r'/?>'),               fmt('#0451a5', bold=True)),
            (QRegularExpression(r'\b[\w:]+(?=\s*=)'), fmt('#e50000')),
            (QRegularExpression(r'"[^"]*"'),           fmt('#a31515')),
            (QRegularExpression(r"'[^']*'"),           fmt('#a31515')),
            (QRegularExpression(r'<!--.*?-->'),        fmt('#008000', italic=True)),
            (QRegularExpression(r'<!\[CDATA\[.*?\]\]>'), fmt('#0451a5')),
            (QRegularExpression(r'<\?.*?\?>'),         fmt('#af00db')),
        ]

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# ── Validation status bar ─────────────────────────────────────────────────────

class _ValidationBar(QWidget):
    """One-line bar that shows the XML validation state."""

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

        self._set_state('idle')

    def _set_state(self, state: str, text: str = ''):
        colors = {
            'idle':  ('#94a3b8', '#f8fafc'),
            'ok':    ('#059669', '#f0fdf4'),
            'error': ('#dc2626', '#fef2f2'),
            'empty': ('#94a3b8', '#f8fafc'),
        }
        fg, bg = colors.get(state, ('#858585', '#1e1e2e'))
        icons  = {'idle': '—', 'ok': '✓', 'error': '✕', 'empty': '—'}
        self.setStyleSheet(f'background:{bg};')
        self._icon.setStyleSheet(f'color:{fg};font-weight:bold;')
        self._icon.setText(icons.get(state, '—'))
        self._msg.setStyleSheet(f'color:{fg};font-size:11px;')
        self._msg.setText(text)

    def set_idle(self):
        self._set_state('idle', 'Open an XML file to begin editing.')

    def set_empty(self):
        self._set_state('empty', 'Empty document.')

    def set_valid(self):
        self._set_state('ok', 'Valid XML  ✓')

    def set_error(self, line: int, col: int, msg: str):
        short = msg.split('\n')[0][:120]
        self._set_state('error', f'Line {line}, Col {col}: {short}')


# ── Find / Replace dialog ─────────────────────────────────────────────────────

class _FindReplaceDialog(QDialog):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setWindowTitle('Find & Replace')
        self.setModal(False)
        self.resize(440, 190)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        find_row = QHBoxLayout()
        find_row.addWidget(QLabel('Find:'))
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText('Search text…')
        self._find_edit.returnPressed.connect(self._find_next)
        find_row.addWidget(self._find_edit)
        layout.addLayout(find_row)

        repl_row = QHBoxLayout()
        repl_row.addWidget(QLabel('Replace:'))
        self._repl_edit = QLineEdit()
        self._repl_edit.setPlaceholderText('Replacement text…')
        repl_row.addWidget(self._repl_edit)
        layout.addLayout(repl_row)

        self._case_cb = QCheckBox('Match case')
        layout.addWidget(self._case_cb)

        btn_row = QHBoxLayout()
        for label, slot in [
            ('Find Next',   self._find_next),
            ('Replace',     self._replace_one),
            ('Replace All', self._replace_all),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._status = QLabel('')
        self._status.setStyleSheet('color:#888;font-size:11px')
        layout.addWidget(self._status)

    def _find_flags(self) -> QTextDocument.FindFlag:
        flags = QTextDocument.FindFlag(0)
        if self._case_cb.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        return flags

    def _find_next(self, wrap: bool = True) -> bool:
        text = self._find_edit.text()
        if not text:
            return False
        found = self._editor.find(text, self._find_flags())
        if not found and wrap:
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._editor.setTextCursor(cursor)
            found = self._editor.find(text, self._find_flags())
        self._status.setText('' if found else 'Not found.')
        return found

    def _replace_one(self):
        text = self._find_edit.text()
        repl = self._repl_edit.text()
        if not text:
            return
        cursor = self._editor.textCursor()
        sel = cursor.selectedText()
        if sel and (
            sel == text if self._case_cb.isChecked() else sel.lower() == text.lower()
        ):
            cursor.insertText(repl)
        self._find_next()

    def _replace_all(self):
        text = self._find_edit.text()
        repl = self._repl_edit.text()
        if not text:
            return
        content = self._editor.toPlainText()
        if self._case_cb.isChecked():
            count = content.count(text)
            new_content = content.replace(text, repl)
        else:
            pattern = _re.compile(_re.escape(text), _re.IGNORECASE)
            count = len(pattern.findall(content))
            new_content = pattern.sub(repl, content)
        self._editor.setPlainText(new_content)
        self._status.setText(f'Replaced {count} occurrence(s).')


# ── WF2 shortcut definitions ──────────────────────────────────────────────────
WRAP_USEREDIT = '<innodReplace userEdit="true">_</innodReplace>'

EMPHASIS_TAGS = [
    ('Alt+B', '<b>…</b>',  '<b>_</b>'),
    ('Alt+I', '<i>…</i>',  '<i>_</i>'),
    ('Alt+U', '<u>…</u>',  '<u>_</u>'),
    ('Alt+S', '<s>…</s>',  '<s>_</s>'),
]

STRUCTURE_TAGS = [
    ('Alt+P', 'innodReplace + <p>',
     '<innodReplace text="&#10;&#10;">_</innodReplace><p>|</p>'),
    ('Alt+L', 'innodLevel + section',
     '<innodLevel level="|"><section>_</section></innodLevel>'),
    ('Alt+Q', 'innodIdentifier',
     '<innodIdentifier>|</innodIdentifier>'),
    ('Alt+H', 'innodHeading',
     '<innodHeading>|</innodHeading>'),
    ('Alt+F', 'innodFootnoteRef',
     '<innodFootnoteRef fid="|" id="" text="">_</innodFootnoteRef>'),
    ('Alt+T', 'innodFootnote',
     '<innodFootnote><footnote>_</footnote></innodFootnote>'),
    ('Alt+M', 'innodImg',
     '<innodImg src="|"><img src="_" /></innodImg>'),
    ('Alt+6', 'innodTable (2×2)',
     '<innodTable><table>\n  <tr><td>|</td><td></td></tr>\n'
     '  <tr><td></td><td></td></tr>\n</table></innodTable>'),
    ('Alt+7', 'inno-ref (manual)',
     '<inno-ref type="manual" href="_">|</inno-ref>'),
]

GENERAL_SHORTCUTS = [
    ('Ctrl+S',          'Save XML (Save As…)'),
    ('Ctrl+Shift+E',    'Wrap selection as <innodReplace userEdit>…</innodReplace>'),
    ('Ctrl+Shift+F',    'Format / pretty-print XML'),
    ('Ctrl+Z / Ctrl+Y', 'Undo / Redo'),
    ('Ctrl+F / Ctrl+H', 'Find / Find & Replace'),
    ('Ctrl+G',          'Go to line'),
    ('Ctrl+/',          'Toggle comment on selection'),
    ('F1',              'Show this Shortcuts help'),
]


# ── Help & Shortcuts dialog ───────────────────────────────────────────────────

class _ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('XML Editor — Help & Shortcuts')
        self.setModal(True)
        self.resize(560, 640)
        self.setStyleSheet('background:#ffffff;')

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        header = QLabel('  ⌨  XML Editor — Help & Shortcuts')
        header.setStyleSheet(
            'font-size:16px;font-weight:bold;color:#1f3a5f;padding:14px;'
            'border-bottom:1px solid #e0e0e0;'
        )
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('border:none;')
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(18, 14, 18, 14)
        bl.setSpacing(14)

        bl.addWidget(self._section('General', [
            (k, d, None) for k, d in GENERAL_SHORTCUTS
        ]))
        bl.addWidget(self._section(
            'Emphasis Tags  (select text first, or inserts empty tag)',
            EMPHASIS_TAGS,
        ))
        bl.addWidget(self._section('Structure Tags  (insert at cursor)', STRUCTURE_TAGS))
        bl.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(14, 8, 14, 12)
        footer.addWidget(QLabel(
            '<span style="color:#888;font-size:11px">Press Esc or click Close.</span>'
        ))
        footer.addStretch()
        close = QPushButton('Got it')
        close.setStyleSheet(
            'QPushButton{background:#2a9d8f;color:#fff;border:none;'
            'padding:6px 18px;border-radius:4px;font-weight:bold;}'
            'QPushButton:hover{background:#21867a;}'
        )
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)

    @staticmethod
    def _kbd(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            'background:#f5f5f5;border:1px solid #ccc;border-radius:4px;'
            'padding:1px 7px;font-family:Consolas,monospace;font-size:11px;color:#333;'
        )
        return lbl

    def _section(self, title: str, rows: list) -> QWidget:
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(6)

        t = QLabel(title)
        t.setStyleSheet('color:#2a6f97;font-size:13px;font-weight:bold;')
        wl.addWidget(t)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(1, 1)
        for r, row in enumerate(rows):
            key, desc = row[0], row[1]
            kbd_wrap = QHBoxLayout()
            kbd_wrap.setContentsMargins(0, 0, 0, 0)
            kbd_wrap.addWidget(self._kbd(key))
            kbd_wrap.addStretch()
            kc = QWidget()
            kc.setLayout(kbd_wrap)
            kc.setFixedWidth(130)
            grid.addWidget(kc, r, 0)
            d = QLabel(desc)
            d.setStyleSheet('color:#444;font-size:12px;')
            d.setWordWrap(True)
            grid.addWidget(d, r, 1)
        wl.addLayout(grid)
        return wrap


# ── Public widget ─────────────────────────────────────────────────────────────

class XmlEditor(QWidget):
    """XML editor with syntax highlighting, line numbers, and live validation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet('background:#f8fafc;border-bottom:1px solid #e2e8f0;')
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(6, 3, 6, 3)
        tb.setSpacing(4)

        def _tbtn(label: str, tip: str) -> QPushButton:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setStyleSheet(
                'QPushButton{background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;'
                'padding:3px 10px;border-radius:3px;font-size:11px;}'
                'QPushButton:hover{background:#e2e8f0;color:#334155;}'
            )
            return b

        self._btn_fmt   = _tbtn('Format XML',  'Pretty-print XML (Ctrl+Shift+F)')
        self._btn_find  = _tbtn('Find',         'Find (Ctrl+F)')
        self._btn_repl  = _tbtn('Replace',      'Find & Replace (Ctrl+H)')
        self._btn_goto  = _tbtn('Go to Line',   'Go to Line (Ctrl+G)')
        self._btn_cmt   = _tbtn('Comment',      'Toggle comment on selection (Ctrl+/)')
        self._btn_undo  = _tbtn('↩ Undo',       'Undo (Ctrl+Z)')
        self._btn_redo  = _tbtn('↪ Redo',       'Redo (Ctrl+Y)')
        self._btn_help  = _tbtn('⌨ Shortcuts',  'Show all editor shortcuts (F1)')

        for btn in [self._btn_fmt, self._btn_find, self._btn_repl,
                    self._btn_goto, self._btn_cmt, self._btn_undo, self._btn_redo]:
            tb.addWidget(btn)
        tb.addStretch()
        tb.addWidget(self._btn_help)
        root.addWidget(toolbar)

        # ── Editor ───────────────────────────────────────────────────────────
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
        root.addWidget(self._edit, 1)

        # ── Validation bar ────────────────────────────────────────────────────
        self._val_bar = _ValidationBar()
        root.addWidget(self._val_bar)

        # ── Validation timer (800 ms debounce) ────────────────────────────────
        self._val_timer = QTimer(self)
        self._val_timer.setSingleShot(True)
        self._val_timer.setInterval(800)
        self._val_timer.timeout.connect(self._run_validation)
        self._edit.document().contentsChanged.connect(self._val_timer.start)

        # ── Wire toolbar ──────────────────────────────────────────────────────
        self._btn_fmt.clicked.connect(self._format_xml)
        self._btn_find.clicked.connect(self._show_find)
        self._btn_repl.clicked.connect(self._show_find_replace)
        self._btn_goto.clicked.connect(self._goto_line)
        self._btn_cmt.clicked.connect(self._toggle_comment)
        self._btn_undo.clicked.connect(self._edit.undo)
        self._btn_redo.clicked.connect(self._edit.redo)
        self._btn_help.clicked.connect(self._show_shortcuts)

        # ── Keyboard shortcuts ────────────────────────────────────────────────
        QShortcut(QKeySequence('Ctrl+Shift+F'), self).activated.connect(self._format_xml)
        QShortcut(QKeySequence('Ctrl+F'),       self).activated.connect(self._show_find)
        QShortcut(QKeySequence('Ctrl+H'),       self).activated.connect(self._show_find_replace)
        QShortcut(QKeySequence('Ctrl+G'),       self).activated.connect(self._goto_line)
        QShortcut(QKeySequence('Ctrl+/'),       self).activated.connect(self._toggle_comment)
        QShortcut(QKeySequence('F1'),           self).activated.connect(self._show_shortcuts)
        QShortcut(QKeySequence('Ctrl+Shift+E'), self).activated.connect(
            lambda: self._insert_template(WRAP_USEREDIT))
        for key, _label, template in EMPHASIS_TAGS + STRUCTURE_TAGS:
            QShortcut(QKeySequence(key), self).activated.connect(
                lambda t=template: self._insert_template(t))

        self._find_dlg: _FindReplaceDialog | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def toPlainText(self) -> str:
        return self._edit.toPlainText()

    def setPlainText(self, text: str):
        self._edit.setPlainText(text)
        # Trigger immediate validation
        self._val_timer.start()

    def document(self):
        return self._edit.document()

    # ── Validation ────────────────────────────────────────────────────────────

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
            line = (e.lineno or 1) - 1   # convert to 0-based
            col  = e.offset or 1
            self._val_bar.set_error(line + 1, col, str(e))
            self._edit.set_error_lines({line})

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _format_xml(self):
        text = self._edit.toPlainText().strip()
        if not text:
            return
        try:
            tree = etree.fromstring(text.encode('utf-8'))
            pretty = etree.tostring(tree, pretty_print=True, encoding='unicode')
            self._edit.setPlainText(pretty)
        except etree.XMLSyntaxError as e:
            QMessageBox.warning(self, 'Format Error',
                                f'Cannot format — invalid XML:\n{e}')

    def _get_find_dialog(self) -> '_FindReplaceDialog':
        if self._find_dlg is None:
            self._find_dlg = _FindReplaceDialog(self._edit, self)
        return self._find_dlg

    def _show_find(self):
        dlg = self._get_find_dialog()
        dlg.show(); dlg.raise_()
        dlg._find_edit.setFocus(); dlg._find_edit.selectAll()

    def _show_find_replace(self):
        dlg = self._get_find_dialog()
        dlg.show(); dlg.raise_()
        dlg._find_edit.setFocus()

    def _goto_line(self):
        total = self._edit.document().blockCount()
        line, ok = QInputDialog.getInt(
            self, 'Go to Line', f'Line number (1–{total}):',
            value=max(1, self._edit.textCursor().blockNumber() + 1),
            minValue=1, maxValue=total,
        )
        if ok:
            block = self._edit.document().findBlockByLineNumber(line - 1)
            cursor = self._edit.textCursor()
            cursor.setPosition(block.position())
            self._edit.setTextCursor(cursor)
            self._edit.ensureCursorVisible()
            self._edit.centerCursor()

    def _insert_template(self, template: str):
        cursor = self._edit.textCursor()
        sel = cursor.selectedText().replace(chr(0x2029), chr(10))

        body = template.replace('_', sel)
        if '|' in body:
            caret_off = body.index('|')
            body = body.replace('|', '')
        elif '_' in template:
            caret_off = template.index('_') + len(sel)
        else:
            caret_off = len(body)

        cursor.insertText(body)
        cursor.setPosition(cursor.position() - (len(body) - caret_off))
        self._edit.setTextCursor(cursor)
        self._edit.setFocus()

    def _show_shortcuts(self):
        _ShortcutsDialog(self).exec()

    def _toggle_comment(self):
        cursor = self._edit.textCursor()
        if cursor.hasSelection():
            start, end = cursor.selectionStart(), cursor.selectionEnd()
        else:
            block = cursor.block()
            start = block.position()
            end   = block.position() + block.length() - 1

        c = self._edit.textCursor()
        c.setPosition(start)
        c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        text = c.selectedText()
        stripped = text.strip()

        c.beginEditBlock()
        if stripped.startswith('<!--') and stripped.endswith('-->'):
            uncommented = text.replace('<!--', '', 1)
            idx = uncommented.rfind('-->')
            uncommented = uncommented[:idx] + uncommented[idx + 3:]
            c.insertText(uncommented.strip())
        else:
            c.insertText(f'<!-- {text.strip()} -->')
        c.endEditBlock()
