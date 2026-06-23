from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextBrowser
from PySide6.QtCore import Qt

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

  /* Emphasis — explicit rules for Qt's HTML renderer */
  b, strong,
  span[style*="font-weight:bold"]   { font-weight: bold; }
  i, em,
  span[style*="font-style:italic"]  { font-style: italic; }
  s, del, strike,
  span[style*="line-through"]       { text-decoration: line-through; color: #888; }

  /* Diff highlights */
  span[style*="background:#ffcccc"] { background: #ffcccc; border-radius: 3px; }
  span[style*="background:#ccffcc"] { background: #ccffcc; border-radius: 3px; }
  span[style*="background:#ffd699"] { background: #ffd699; border-radius: 3px; }
</style>
"""

_PLACEHOLDER = _CSS + """
<body>
  <p style="color:#aaa;font-style:italic;margin-top:20px">No document loaded.</p>
</body>
"""


class DocumentPanel(QWidget):
    def __init__(self, title: str = '', parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if title:
            header = QLabel(title)
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setStyleSheet(
                'background:#2b2d42;color:#edf2f4;padding:7px;'
                'font-weight:bold;font-size:13px;letter-spacing:0.5px;'
            )
            layout.addWidget(header)

        self.browser = QTextBrowser()
        self.browser.setStyleSheet('background:#ffffff;border:none;')
        self.browser.setOpenLinks(False)
        self.browser.setHtml(_PLACEHOLDER)
        layout.addWidget(self.browser)

    def set_html(self, content: str):
        self.browser.setHtml(f'<html><head>{_CSS}</head><body>{content}</body></html>')

    def clear(self):
        self.browser.setHtml(_PLACEHOLDER)
