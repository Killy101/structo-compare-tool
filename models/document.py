import html as _html
from dataclasses import dataclass, field
from typing import List


@dataclass
class TextSpan:
    text: str
    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    underline: bool = False

    def to_html(self) -> str:
        t = _html.escape(self.text)
        styles: list[str] = []
        decorations: list[str] = []

        if self.bold:
            styles.append('font-weight:bold')
        if self.italic:
            styles.append('font-style:italic')
        if self.underline:
            decorations.append('underline')
        if self.strikethrough:
            decorations.append('line-through')
            styles.append('color:#888')

        if decorations:
            styles.append('text-decoration:' + ' '.join(decorations))

        if styles:
            return f'<span style="{";".join(styles)}">{t}</span>'
        return t


@dataclass
class TextBlock:
    spans: List[TextSpan] = field(default_factory=list)

    def plain_text(self) -> str:
        return ''.join(s.text for s in self.spans)

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
