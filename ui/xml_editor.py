from PySide6.QtWidgets import QTextEdit
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont
)
from PySide6.QtCore import QRegularExpression


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
            # XML tags  <tag ...>
            (QRegularExpression(r'</?[\w:]+'), fmt('#569cd6', bold=True)),
            # Closing bracket / self-close
            (QRegularExpression(r'/?>'), fmt('#569cd6', bold=True)),
            # Attribute names
            (QRegularExpression(r'\b[\w:]+(?=\s*=)'), fmt('#9cdcfe')),
            # Attribute values (double-quoted)
            (QRegularExpression(r'"[^"]*"'), fmt('#ce9178')),
            # Attribute values (single-quoted)
            (QRegularExpression(r"'[^']*'"), fmt('#ce9178')),
            # Comments
            (QRegularExpression(r'<!--.*?-->'), fmt('#6a9955', italic=True)),
            # CDATA
            (QRegularExpression(r'<!\[CDATA\[.*?\]\]>'), fmt('#d4d4aa')),
            # Processing instructions
            (QRegularExpression(r'<\?.*?\?>'), fmt('#c586c0')),
        ]

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class XmlEditor(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        mono = QFont('Consolas', 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(mono)
        self.setStyleSheet(
            'background:#1e1e1e; color:#d4d4d4; border:none; padding:8px;'
        )
        self.setPlaceholderText('Open an XML file to edit...')
        self.setTabStopDistance(28)
        self._highlighter = _XmlHighlighter(self.document())
