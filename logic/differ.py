import difflib
import html as _html
from dataclasses import dataclass
from models.document import Document
from typing import List, Tuple

# ── Highlight palette ────────────────────────────────────────────────────────
BG_DELETE   = '#ffcccc'   # pink-red  — deleted text
BG_INSERT   = '#ccffcc'   # green     — added text
BG_MOD_OLD  = '#ffcccc'   # pink-red  — old side of a modification
BG_MOD_NEW  = '#ffd699'   # orange    — new side of a modification


# ── Token: one word with its source emphasis ─────────────────────────────────
@dataclass
class _Token:
    word: str
    bold: bool = False
    italic: bool = False
    src_strike: bool = False   # strikethrough from the source document

    @property
    def is_newline(self) -> bool:
        return self.word == '\n'

    def render(self, bg: str = '', diff_strike: bool = False) -> str:
        """Render word with emphasis + optional diff highlight, all in one span."""
        if self.is_newline:
            return '<br/>'

        t = _html.escape(self.word)
        styles: list[str] = []
        decorations: list[str] = []

        if self.bold:
            styles.append('font-weight:bold')
        if self.italic:
            styles.append('font-style:italic')

        # Source strikethrough (grey) OR diff deletion strikethrough (red text)
        if self.src_strike or diff_strike:
            decorations.append('line-through')

        if decorations:
            styles.append('text-decoration:' + ' '.join(decorations))

        if bg:
            styles.append(f'background:{bg}')
            styles.append('border-radius:3px')
            styles.append('padding:0 2px')

        if styles:
            return f'<span style="{";".join(styles)}">{t}</span>'
        return t


def _tokenize(doc: Document) -> List[_Token]:
    tokens: List[_Token] = []
    for block in doc.blocks:
        for span in block.spans:
            for word in span.text.split():
                tokens.append(_Token(
                    word=word,
                    bold=span.bold,
                    italic=span.italic,
                    src_strike=span.strikethrough,
                ))
        tokens.append(_Token(word='\n'))
    return tokens


def _plain(tokens: List[_Token], i1: int, i2: int) -> str:
    return ' '.join(t.word for t in tokens[i1:i2] if not t.is_newline).strip()


# ── Main diff function ───────────────────────────────────────────────────────
def build_diff_html(old_doc: Document, new_doc: Document) -> Tuple[str, str, str]:
    """Returns (old_panel_html, new_panel_html, sidebar_html)."""
    old_tok = _tokenize(old_doc)
    new_tok = _tokenize(new_doc)

    matcher = difflib.SequenceMatcher(
        None,
        [t.word for t in old_tok],
        [t.word for t in new_tok],
        autojunk=False,
    )

    old_parts: List[str] = []
    new_parts: List[str] = []
    sidebar_items: List[str] = []
    change_count = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():

        if tag == 'equal':
            for tok in old_tok[i1:i2]:
                old_parts.append(tok.render() + ('' if tok.is_newline else ' '))
            for tok in new_tok[j1:j2]:
                new_parts.append(tok.render() + ('' if tok.is_newline else ' '))

        elif tag == 'delete':
            for tok in old_tok[i1:i2]:
                old_parts.append(
                    tok.render(bg=BG_DELETE, diff_strike=True)
                    + ('' if tok.is_newline else ' ')
                )
            txt = _plain(old_tok, i1, i2)
            if txt:
                change_count += 1
                sidebar_items.append(
                    f'<div class="ch del">'
                    f'<span class="badge bdel">Deleted</span>'
                    f'<span class="txt" style="text-decoration:line-through;color:#c0392b">'
                    f'{_html.escape(txt)}</span>'
                    f'</div>'
                )

        elif tag == 'insert':
            for tok in new_tok[j1:j2]:
                new_parts.append(
                    tok.render(bg=BG_INSERT)
                    + ('' if tok.is_newline else ' ')
                )
            txt = _plain(new_tok, j1, j2)
            if txt:
                change_count += 1
                sidebar_items.append(
                    f'<div class="ch add">'
                    f'<span class="badge badd">Added</span>'
                    f'<span class="txt" style="color:#27ae60">'
                    f'{_html.escape(txt)}</span>'
                    f'</div>'
                )

        elif tag == 'replace':
            for tok in old_tok[i1:i2]:
                old_parts.append(
                    tok.render(bg=BG_MOD_OLD, diff_strike=True)
                    + ('' if tok.is_newline else ' ')
                )
            for tok in new_tok[j1:j2]:
                new_parts.append(
                    tok.render(bg=BG_MOD_NEW)
                    + ('' if tok.is_newline else ' ')
                )
            old_txt = _plain(old_tok, i1, i2)
            new_txt = _plain(new_tok, j1, j2)
            if old_txt or new_txt:
                change_count += 1
                sidebar_items.append(
                    f'<div class="ch mod">'
                    f'<span class="badge bmod">Modified</span>'
                    f'<span class="txt">'
                    f'<span style="text-decoration:line-through;color:#c0392b">'
                    f'{_html.escape(old_txt)}</span>'
                    f'<span class="arrow"> ➜ </span>'
                    f'<span style="color:#e67e22">{_html.escape(new_txt)}</span>'
                    f'</span>'
                    f'</div>'
                )

    # ── Sidebar HTML ─────────────────────────────────────────────────────────
    css = """<style>
      body { font-family:Arial,sans-serif; font-size:12px;
             background:#1e1e2e; color:#cdd6f4; margin:0; padding:8px; }
      .header { font-size:13px; font-weight:bold; color:#cba6f7;
                margin-bottom:8px; padding-bottom:6px;
                border-bottom:1px solid #45475a; }
      .count  { color:#a6adc8; font-size:11px; font-weight:normal; }
      .ch     { margin:5px 0; padding:6px 8px; border-radius:5px;
                background:#313244; }
      .del    { border-left:3px solid #f38ba8; }
      .add    { border-left:3px solid #a6e3a1; }
      .mod    { border-left:3px solid #ffd699; }
      .badge  { display:inline-block; font-size:10px; font-weight:bold;
                padding:1px 6px; border-radius:3px; margin-right:6px;
                vertical-align:middle; }
      .bdel   { background:#f38ba8; color:#1e1e2e; }
      .badd   { background:#a6e3a1; color:#1e1e2e; }
      .bmod   { background:#ffd699; color:#1e1e2e; }
      .arrow  { color:#89b4fa; font-weight:bold; }
      .empty  { color:#585b70; font-style:italic; text-align:center;
                margin-top:40px; }
    </style>"""

    if sidebar_items:
        header = (
            f'<div class="header">Changes '
            f'<span class="count">({change_count} found)</span></div>'
        )
        sidebar_html = css + '<body>' + header + '\n'.join(sidebar_items) + '</body>'
    else:
        sidebar_html = css + '<body><div class="empty">No changes detected.</div></body>'

    return ''.join(old_parts), ''.join(new_parts), sidebar_html
