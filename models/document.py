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
    # Leading indentation, expressed in whitespace "units" so that the
    # editable text panels and the diff view can reproduce the original
    # document layout (nesting of lists, indented paragraphs, etc.).
    indent: int = 0
    # Coarse structural role, used purely for display fidelity / styling.
    #   'normal' | 'heading' | 'list' | 'blank'
    kind: str = 'normal'

    def is_blank(self) -> bool:
        return self.kind == 'blank' or not any(s.text.strip() for s in self.spans)

    def plain_text(self) -> str:
        """Return a space‑collapsed version of the block’s text (diff input)."""
        # Normalise internal whitespace – PDF extractors and the line‑merge step
        # often insert extra spaces; collapse any run to a single space.
        joined = ' '.join(s.text for s in self.spans if s.text)
        return _re.sub(r'\s+', ' ', joined).strip()

    def display_text(self) -> str:
        """Indented, layout‑preserving text for the editable panels."""
        body = ' '.join(s.text for s in self.spans if s.text)
        body = _re.sub(r'\s+', ' ', body).strip()
        if not body:
            return ''
        return (' ' * self.indent) + body

    def to_html(self) -> str:
        return ''.join(s.to_html() for s in self.spans)


@dataclass
class Document:
    blocks: List[TextBlock] = field(default_factory=list)
    raw_xml: str = ''

    def plain_text(self) -> str:
        return '\n'.join(b.plain_text() for b in self.blocks)

    def display_text(self) -> str:
        """Faithful, editable multi‑line representation of the document."""
        return '\n'.join(b.display_text() for b in self.blocks)

    def to_html(self) -> str:
        parts = []
        for block in self.blocks:
            inner = block.to_html()
            if inner.strip():
                parts.append(f'<p style="margin:3px 0;line-height:1.6">{inner}</p>')
        return '\n'.join(parts)