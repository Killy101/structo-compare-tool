from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
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
  span[style*="background:#ddd0ff"] { background: #ddd0ff; border-radius: 3px; }
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
        self.browser.scrollToAnchor(anchor)

    def clear(self):
        self.browser.setHtml(_PLACEHOLDER)

    def scroll_fraction(self) -> float:
        sb = self.browser.verticalScrollBar()
        mx = sb.maximum()
        return sb.value() / mx if mx > 0 else 0.0

    def set_scroll_fraction(self, frac: float):
        sb = self.browser.verticalScrollBar()
        sb.setValue(int(sb.maximum() * frac))
