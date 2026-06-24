# ui/xml_editor.py
import re as _re
from lxml import etree  # type: ignore[attr-defined]  # C-extension, no stubs

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPlainTextEdit, QTextEdit,
    QPushButton, QLabel, QLineEdit, QCheckBox,
    QMessageBox, QInputDialog, QScrollArea, QDialog, QToolTip,
)
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QKeySequence, QShortcut, QTextCursor, QTextDocument, QPainter,
)
from PySide6.QtCore import QRegularExpression, Qt, QSize, QRect, QTimer, QEvent


# -----------------------------------------------------------------------
# Line‑number gutter (unchanged)
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
# Code editor – now safe auto‑close and modest cursor‑aware logic
# -----------------------------------------------------------------------
class _CodeEdit(QPlainTextEdit):
    """Plain‑text editor with line numbers, validation markers,
    and an *auto‑close‑tag* feature that works anywhere on the line."""
    _OPEN_TAG_RE = _re.compile(r'<([A-Za-z_][\w:.-]*)(?:\s[^<>]*)?>$')

    def __init__(self):
        super().__init__()
        self._line_area = _LineNumberArea(self)
        self._err_lines: set[int] = set()

        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._repaint_current_line)
        self._update_margin()

    # -------------------------------------------------------------------
    # Geometry helpers (unchanged)
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
                                   self._line_area.width(),
                                   rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(cr.left(), cr.top(),
                                    self._line_number_width(),
                                    cr.height())

    # -------------------------------------------------------------------
    # Painting line numbers (unchanged)
    # -------------------------------------------------------------------
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
        w = self._line_area.width()

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

    # -------------------------------------------------------------------
    # Current‑line + error‑line extra selections
    # -------------------------------------------------------------------
    def _repaint_current_line(self):
        selections = []

        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor('#f1f5f9'))
            sel.format.setProperty(0x100000 + 1, True)   # FullWidthSelection
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            selections.append(sel)

        for line_num in self._err_lines:
            block = self.document().findBlockByNumber(line_num)
            if block.isValid():
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(QColor('#fee2e2'))
                sel.format.setProperty(0x100000 + 1, True)
                sel.cursor = QTextCursor(block)
                selections.append(sel)

        self.setExtraSelections(selections)

    def set_error_lines(self, lines: set[int]):
        self._err_lines = lines
        self._repaint_current_line()

    # -------------------------------------------------------------------
    # Safer auto‑close tag – works even if the cursor is **not**
    # at the end of the line.
    # -------------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.text() == '>':
            cursor = self.textCursor()
            block = cursor.block()
            # text *up to* the cursor (including the character that will be inserted)
            line_up_to_cursor = block.text()[:cursor.positionInBlock()] + '>'
            m = self._OPEN_TAG_RE.search(line_up_to_cursor)
            if m and not line_up_to_cursor.rstrip().endswith('/>') \
                    and not line_up_to_cursor.lstrip().startswith('</'):
                # Insert the '>' first (so the document updates)
                super().keyPressEvent(event)
                tag = m.group(1)
                # Insert closing tag and place the caret inside it
                c = self.textCursor()
                c.insertText(f'</{tag}>')
                # Move cursor left to sit **before** the closing tag
                for _ in range(len(tag) + 3):
                    c.movePosition(QTextCursor.MoveOperation.Left,
                                   QTextCursor.MoveMode.MoveAnchor)
                self.setTextCursor(c)
                return
        super().keyPressEvent(event)

    # -------------------------------------------------------------------
    # Event filter – show validation error tooltip on hover
    # -------------------------------------------------------------------
    def eventFilter(self, obj, event):
        if obj is self.viewport() and event.type() == QEvent.Type.ToolTip:
            cursor = self.cursorForPosition(event.pos())
            line = cursor.blockNumber()
            if line in self._err_lines:
                # Pull the error message from the validation bar (shared state)
                # The validation bar lives inside XmlEditor; we ask the parent.
                parent = self.parent()
                if isinstance(parent, XmlEditor):
                    msg = parent._val_bar._msg.text()
                else:
                    msg = "XML error"
                QToolTip.showText(event.globalPos(), msg, self)
            else:
                QToolTip.hideText()
            return True
        return super().eventFilter(obj, event)


# -----------------------------------------------------------------------
# Syntax highlighter (unchanged)
# -----------------------------------------------------------------------
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
            (QRegularExpression(r'\b[\w:]+(?=\s*=)'),  fmt('#e50000')),
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


# -----------------------------------------------------------------------
# Validation bar (unchanged, only minor docstring tweak)
# -----------------------------------------------------------------------
class _ValidationBar(QWidget):
    """One‑line status bar that shows XML validation state."""
    def __init__(self):
        super().__init__()
        self.setFixedHeight(22)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(6)

        self._icon = QLabel('—')
        self._icon.setFixedWidth(14)
        self._msg = QLabel('Open an XML file to begin editing.')
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
        icons = {'idle': '—', 'ok': '✓', 'error': '✕', 'empty': '—'}
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


# -----------------------------------------------------------------------
# Find / Replace dialog (unchanged)
# -----------------------------------------------------------------------
class _FindReplaceDialog(QDialog):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setWindowTitle('Find & Replace')
        self.setModal(False)
        self.resize(440, 190)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Find ───────────────────────
        find_row = QHBoxLayout()
        find_row.addWidget(QLabel('Find:'))
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText('Search text…')
        self._find_edit.returnPressed.connect(self._find_next)
        find_row.addWidget(self._find_edit)
        layout.addLayout(find_row)

        # ── Replace ────────────────────
        repl_row = QHBoxLayout()
        repl_row.addWidget(QLabel('Replace:'))
        self._repl_edit = QLineEdit()
        self._repl_edit.setPlaceholderText('Replacement text…')
        repl_row.addWidget(self._repl_edit)
        layout.addLayout(repl_row)

        # ── Options ────────────────────
        self._case_cb = QCheckBox('Match case')
        layout.addWidget(self._case_cb)

        # ── Buttons ────────────────────
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
            cur = self._editor.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.Start)
            self._editor.setTextCursor(cur)
            found = self._editor.find(text, self._find_flags())
        self._status.setText('' if found else 'Not found.')
        return found

    def _replace_one(self):
        text = self._find_edit.text()
        repl = self._repl_edit.text()
        if not text:
            return
        cur = self._editor.textCursor()
        sel = cur.selectedText()
        if sel and (
            sel == text if self._case_cb.isChecked() else sel.lower() == text.lower()
        ):
            cur.insertText(repl)
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


# -----------------------------------------------------------------------
# Shortcuts dialog
# -----------------------------------------------------------------------
class _ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Keyboard Shortcuts')
        self.setModal(True)
        self.resize(420, 260)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        shortcuts = (
            'Ctrl+Shift+F   Format XML\n'
            'Ctrl+F         Find\n'
            'Ctrl+H         Replace\n'
            'Ctrl+G         Go to Line\n'
            'Ctrl+/         Toggle comment\n'
            'Ctrl+Z         Undo\n'
            'Ctrl+Y         Redo\n'
            'F1             Show shortcuts'
        )

        label = QLabel(f'<pre>{shortcuts}</pre>')
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)

        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


# -----------------------------------------------------------------------
# Public widget – revamped to install the tooltip filter
# -----------------------------------------------------------------------
class XmlEditor(QWidget):
    """XML editor with syntax highlighting, line numbers,
    live validation, and tooltip error messages."""
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ─────────────────────
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

        self._btn_fmt   = _tbtn('Format XML',  'Pretty‑print (Ctrl+Shift+F)')
        self._btn_find  = _tbtn('Find',         'Find (Ctrl+F)')
        self._btn_repl  = _tbtn('Replace',      'Find & Replace (Ctrl+H)')
        self._btn_goto  = _tbtn('Go to Line',   'Ctrl+G')
        self._btn_cmt   = _tbtn('Comment',      'Toggle comment (Ctrl+/)')
        self._btn_undo  = _tbtn('↩ Undo',       'Ctrl+Z')
        self._btn_redo  = _tbtn('↪ Redo',       'Ctrl+Y')
        self._btn_help  = _tbtn('⌨ Shortcuts',  'F1')

        for btn in (self._btn_fmt, self._btn_find, self._btn_repl,
                    self._btn_goto, self._btn_cmt,
                    self._btn_undo, self._btn_redo):
            tb.addWidget(btn)

        tb.addStretch()
        tb.addWidget(self._btn_help)
        root.addWidget(toolbar)

        # ── Editor ─────────────────────
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

        # Install the tooltip filter **after** the editor is created
        self._edit.viewport().installEventFilter(self._edit)

        # ── Validation bar ─────────────────
        self._val_bar = _ValidationBar()
        root.addWidget(self._val_bar)

        # ── Debounced validation timer ─────
        self._val_timer = QTimer(self)
        self._val_timer.setSingleShot(True)
        self._val_timer.setInterval(800)
        self._val_timer.timeout.connect(self._run_validation)
        self._edit.document().contentsChanged.connect(self._val_timer.start)

        # ── Toolbar connections ───────────────
        self._btn_fmt.clicked.connect(self._format_xml)
        self._btn_find.clicked.connect(self._show_find)
        self._btn_repl.clicked.connect(self._show_find_replace)
        self._btn_goto.clicked.connect(self._goto_line)
        self._btn_cmt.clicked.connect(self._toggle_comment)
        self._btn_undo.clicked.connect(self._edit.undo)
        self._btn_redo.clicked.connect(self._edit.redo)
        self._btn_help.clicked.connect(self._show_shortcuts)

        # ── Keyboard shortcuts ───────────────
        QShortcut(QKeySequence('Ctrl+Shift+F'), self).activated.connect(self._format_xml)
        QShortcut(QKeySequence('Ctrl+F'),       self).activated.connect(self._show_find)
        QShortcut(QKeySequence('Ctrl+H'),       self).activated.connect(self._show_find_replace)
        QShortcut(QKeySequence('Ctrl+G'),       self).activated.connect(self._goto_line)
        QShortcut(QKeySequence('Ctrl+/'),       self).activated.connect(self._toggle_comment)
        QShortcut(QKeySequence('F1'),           self).activated.connect(self._show_shortcuts)

        # Find‑replace dialog lives lazily
        self._find_dlg: _FindReplaceDialog | None = None

    # -------------------------------------------------------------------
    # Public API used by MainWindow
    # -------------------------------------------------------------------
    def toPlainText(self) -> str:
        return self._edit.toPlainText()

    def setPlainText(self, text: str):
        self._edit.setPlainText(text)
        self._val_timer.start()          # immediate validation

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
            etree.fromstring(text.encode('utf‑8'))
            self._val_bar.set_valid()
            self._edit.set_error_lines(set())
        except etree.XMLSyntaxError as e:
            line = (e.lineno or 1) - 1      # 0‑based for the gutter
            col = e.offset or 1
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
            tree = etree.fromstring(txt.encode('utf‑8'))
            pretty = etree.tostring(tree, pretty_print=True,
                                    encoding='unicode')
            self._edit.setPlainText(pretty)
        except etree.XMLSyntaxError as e:
            QMessageBox.warning(self, 'Format Error',
                                f'Cannot format – invalid XML:\n{e}')

    def _get_find_dialog(self) -> _FindReplaceDialog:
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
            self, 'Go to Line',
            f'Line number (1‑{total}):',
            value=self._edit.textCursor().blockNumber() + 1,
            minValue=1, maxValue=total
        )
        if ok:
            block = self._edit.document().findBlockByNumber(line - 1)
            cur = self._edit.textCursor()
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
        txt = sel_cur.selectedText()
        stripped = txt.strip()

        sel_cur.beginEditBlock()
        if stripped.startswith('<!--') and stripped.endswith('-->'):
            # uncomment – preserve original indentation
            uncommented = stripped[4:-3].strip()
            sel_cur.insertText(uncommented)
        else:
            sel_cur.insertText(f'<!-- {txt.strip()} -->')
        sel_cur.endEditBlock()

    def _show_shortcuts(self):
        _ShortcutsDialog(self).exec()