import re as _re
from lxml import etree

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QDialog, QLabel, QLineEdit, QCheckBox, QDialogButtonBox,
    QMessageBox, QInputDialog,
)
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QKeySequence, QShortcut, QTextCursor, QTextDocument,
)
from PySide6.QtCore import QRegularExpression, Qt


class _CodeEdit(QTextEdit):
    """QTextEdit with XML auto-close-tag behaviour."""

    _OPEN_TAG_RE = _re.compile(r'<([A-Za-z_][\w:.-]*)(?:\s[^<>]*)?>$')

    def keyPressEvent(self, event):
        # Auto-close: when user types '>' that completes an opening tag,
        # insert the matching closing tag and place the cursor between them.
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
            (QRegularExpression(r'</?[\w:]+'),        fmt('#569cd6', bold=True)),
            (QRegularExpression(r'/?>'),               fmt('#569cd6', bold=True)),
            (QRegularExpression(r'\b[\w:]+(?=\s*=)'), fmt('#9cdcfe')),
            (QRegularExpression(r'"[^"]*"'),           fmt('#ce9178')),
            (QRegularExpression(r"'[^']*'"),           fmt('#ce9178')),
            (QRegularExpression(r'<!--.*?-->'),        fmt('#6a9955', italic=True)),
            (QRegularExpression(r'<!\[CDATA\[.*?\]\]>'), fmt('#d4d4aa')),
            (QRegularExpression(r'<\?.*?\?>'),         fmt('#c586c0')),
        ]

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class _FindReplaceDialog(QDialog):
    def __init__(self, editor: QTextEdit, parent=None):
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
            ('Find Next',    self._find_next),
            ('Replace',      self._replace_one),
            ('Replace All',  self._replace_all),
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


class XmlEditor(QWidget):
    """XML editor widget with syntax highlighting and editor shortcuts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet(
            'background:#252526;border-bottom:1px solid #3e3e3e;'
        )
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(6, 3, 6, 3)
        tb.setSpacing(4)

        def _tbtn(label: str, tip: str) -> QPushButton:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setStyleSheet(
                'QPushButton{background:#3e3e3e;color:#ccc;border:none;'
                'padding:3px 10px;border-radius:3px;font-size:11px;}'
                'QPushButton:hover{background:#505050;}'
            )
            return b

        self._btn_fmt   = _tbtn('Format XML',  'Pretty-print XML (Ctrl+Shift+F)')
        self._btn_find  = _tbtn('Find',         'Find (Ctrl+F)')
        self._btn_repl  = _tbtn('Replace',      'Find & Replace (Ctrl+H)')
        self._btn_goto  = _tbtn('Go to Line',   'Go to Line (Ctrl+G)')
        self._btn_cmt   = _tbtn('Comment',      'Toggle comment on selection (Ctrl+/)')
        self._btn_undo  = _tbtn('↩ Undo',       'Undo (Ctrl+Z)')
        self._btn_redo  = _tbtn('↪ Redo',       'Redo (Ctrl+Y)')

        for btn in [self._btn_fmt, self._btn_find, self._btn_repl,
                    self._btn_goto, self._btn_cmt, self._btn_undo, self._btn_redo]:
            tb.addWidget(btn)
        tb.addStretch()
        root.addWidget(toolbar)

        # ── Editor ───────────────────────────────────────────────────────────
        self._edit = _CodeEdit()
        mono = QFont('Consolas', 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._edit.setFont(mono)
        self._edit.setStyleSheet(
            'background:#1e1e1e; color:#d4d4d4; border:none; padding:8px;'
        )
        self._edit.setPlaceholderText('Open an XML file to edit…')
        self._edit.setTabStopDistance(28)
        self._highlighter = _XmlHighlighter(self._edit.document())
        root.addWidget(self._edit)

        # ── Wire toolbar buttons ──────────────────────────────────────────────
        self._btn_fmt.clicked.connect(self._format_xml)
        self._btn_find.clicked.connect(self._show_find)
        self._btn_repl.clicked.connect(self._show_find_replace)
        self._btn_goto.clicked.connect(self._goto_line)
        self._btn_cmt.clicked.connect(self._toggle_comment)
        self._btn_undo.clicked.connect(self._edit.undo)
        self._btn_redo.clicked.connect(self._edit.redo)

        # ── Keyboard shortcuts ────────────────────────────────────────────────
        QShortcut(QKeySequence('Ctrl+Shift+F'), self).activated.connect(self._format_xml)
        QShortcut(QKeySequence('Ctrl+F'),       self).activated.connect(self._show_find)
        QShortcut(QKeySequence('Ctrl+H'),       self).activated.connect(self._show_find_replace)
        QShortcut(QKeySequence('Ctrl+G'),       self).activated.connect(self._goto_line)
        QShortcut(QKeySequence('Ctrl+/'),       self).activated.connect(self._toggle_comment)

        self._find_dlg: _FindReplaceDialog | None = None

    # ── Public API (mirrors QTextEdit) ────────────────────────────────────────
    def toPlainText(self) -> str:
        return self._edit.toPlainText()

    def setPlainText(self, text: str):
        self._edit.setPlainText(text)

    def document(self):
        return self._edit.document()

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
            QMessageBox.warning(self, 'Format Error', f'Cannot format — invalid XML:\n{e}')

    def _get_find_dialog(self) -> '_FindReplaceDialog':
        if self._find_dlg is None:
            self._find_dlg = _FindReplaceDialog(self._edit, self)
        return self._find_dlg

    def _show_find(self):
        dlg = self._get_find_dialog()
        dlg.show()
        dlg.raise_()
        dlg._find_edit.setFocus()
        dlg._find_edit.selectAll()

    def _show_find_replace(self):
        dlg = self._get_find_dialog()
        dlg.show()
        dlg.raise_()
        dlg._find_edit.setFocus()

    def _goto_line(self):
        total = self._edit.document().blockCount()
        line, ok = QInputDialog.getInt(
            self, 'Go to Line', f'Line number (1–{total}):',
            value=1, minValue=1, maxValue=total,
        )
        if ok:
            block = self._edit.document().findBlockByLineNumber(line - 1)
            cursor = self._edit.textCursor()
            cursor.setPosition(block.position())
            self._edit.setTextCursor(cursor)
            self._edit.ensureCursorVisible()

    def _toggle_comment(self):
        """Wrap/unwrap the selected text (or current line) in an XML comment."""
        cursor = self._edit.textCursor()
        if cursor.hasSelection():
            start, end = cursor.selectionStart(), cursor.selectionEnd()
        else:
            block = cursor.block()
            start, end = block.position(), block.position() + block.length() - 1

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
