# models/document.py
import html as _html
import re as _re
from dataclasses import dataclass, field
from typing import List


@dataclass
class TextSpan:
    """A single run of text with its styling flags."""
    text: str
    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    underline: bool = False

    # --------------------------------------------------------------------
    # Produce a **canonical** style string – sorted, no duplicates.
    # --------------------------------------------------------------------
    def _style_key(self) -> str:
        parts: List[str] = []
        if self.bold:
            parts.append('font-weight:bold')
        if self.italic:
            parts.append('font-style:italic')
        if self.underline:
            parts.append('text-decoration:underline')
        if self.strikethrough:
            parts.append('text-decoration:line-through')
            parts.append('color:#888')               # only for strikethrough
        # sorting makes the string deterministic → diff‑stable
        return ';'.join(sorted(parts))

    # --------------------------------------------------------------------
    # Public HTML rendering – uses the canonical style key.
    # --------------------------------------------------------------------
    def to_html(self) -> str:
        escaped = _html.escape(self.text)
        style = self._style_key()
        if style:
            return f'<span style="{style}">{escaped}</span>'
        return escaped

    # --------------------------------------------------------------------
    # For debugging / logging.
    # --------------------------------------------------------------------
    def __repr__(self) -> str:      # pragma: no cover
        return f"<TextSpan {self.text!r} b={self.bold} i={self.italic} u={self.underline} s={self.strikethrough}>"
    

@dataclass
class TextBlock:
    spans: List[TextSpan] = field(default_factory=list)

    def plain_text(self) -> str:
        """Return a space‑collapsed version of the block’s text."""
        # Normalise internal whitespace – PDF extractors often insert extra spaces.
        return ' '.join(s.text for s in self.spans if s.text).strip()

    def to_html(self) -> str:
        return ''.join(s.to_html() for s in self.spans)


@dataclass
class Document:
    blocks: List[TextBlock] = field(default_factory=list)
    raw_xml: str = ''

    def plain_text(self) -> str:
        return '\n'.join(b.plain_text() for b in self.blocks)

    def to_html(self) -> str:
        parts = []
        for block in self.blocks:
            inner = block.to_html()
            if inner.strip():
                parts.append(f'<p style="margin:3px 0;line-height:1.6">{inner}</p>')
        return '\n'.join(parts)