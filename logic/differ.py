import difflib
import html as _html
import re as _re
from dataclasses import dataclass
from models.document import Document, TextBlock
from typing import List, Tuple


# Collapse all whitespace (incl. non-breaking spaces) so that paragraphs which
# differ only by PDF-extraction whitespace noise are treated as identical.
def _norm(text: str) -> str:
    return _re.sub(r'\s+', ' ', text.replace('\xa0', ' ')).strip()


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


# Minimum similarity for two paragraphs in a replace-region to be considered
# "the same paragraph, modified" rather than an unrelated delete + add.
_PAIR_THRESHOLD = 0.4


def _align_replace(old_slice: List[TextBlock],
                   new_slice: List[TextBlock]) -> List[tuple]:
    """
    Align two runs of paragraphs that the block-level matcher flagged as a
    'replace'. Instead of naive positional pairing, walk both lists and pair
    blocks by text similarity so shifted/revoked items are not mispaired.

    Returns an ordered list of operations:
        ('pair', old_block, new_block)
        ('del',  old_block, None)
        ('add',  None,      new_block)
    """
    old_n = [_norm(b.plain_text()) for b in old_slice]
    new_n = [_norm(b.plain_text()) for b in new_slice]

    ops: List[tuple] = []
    i = j = 0
    n_old, n_new = len(old_slice), len(new_slice)

    while i < n_old and j < n_new:
        r = _ratio(old_n[i], new_n[j])
        if r >= _PAIR_THRESHOLD:
            ops.append(('pair', old_slice[i], new_slice[j]))
            i += 1
            j += 1
            continue

        # Look ahead to decide whether the current old block was deleted or the
        # current new block was inserted (pick the move that yields a better
        # upcoming match).
        r_del = _ratio(old_n[i + 1], new_n[j]) if i + 1 < n_old else 0.0
        r_ins = _ratio(old_n[i], new_n[j + 1]) if j + 1 < n_new else 0.0

        if r_ins > r_del:
            ops.append(('add', None, new_slice[j]))
            j += 1
        else:
            ops.append(('del', old_slice[i], None))
            i += 1

    while i < n_old:
        ops.append(('del', old_slice[i], None))
        i += 1
    while j < n_new:
        ops.append(('add', None, new_slice[j]))
        j += 1

    return ops

# ── Highlight palette ────────────────────────────────────────────────────────
BG_DELETE   = '#ffb3b3'   # pink-red  — deleted text
BG_INSERT   = '#b3ffb3'   # green     — added text
BG_MOD_OLD  = '#ffd6d6'   # light pink — old side of a modification
BG_MOD_NEW  = '#ffffa0'   # yellow    — new side of a modification
BG_EMPHASIS = '#ddd0ff'   # purple    — emphasis-only change


# ── Token: one word with its source formatting ───────────────────────────────
@dataclass
class _Token:
    word: str
    bold: bool = False
    italic: bool = False
    src_strike: bool = False
    underline: bool = False

    @property
    def is_newline(self) -> bool:
        return self.word == '\n'

    @property
    def fmt_key(self) -> tuple:
        return (self.bold, self.italic, self.src_strike, self.underline)

    def render(self, bg: str = '', diff_strike: bool = False) -> str:
        if self.is_newline:
            return '<br/>'
        t = _html.escape(self.word)
        styles: list[str] = []
        decorations: list[str] = []

        if self.bold:
            styles.append('font-weight:bold')
        if self.italic:
            styles.append('font-style:italic')
        if self.underline:
            decorations.append('underline')
        if self.src_strike:
            decorations.append('line-through')
            if not bg:
                styles.append('color:#888')
        elif diff_strike:
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


def _block_tokens(block: TextBlock) -> List[_Token]:
    tokens: List[_Token] = []
    for span in block.spans:
        for word in span.text.split():
            if word:
                tokens.append(_Token(
                    word=word,
                    bold=span.bold,
                    italic=span.italic,
                    src_strike=span.strikethrough,
                    underline=span.underline,
                ))
    return tokens


def _render_plain(block: TextBlock) -> str:
    parts = []
    for span in block.spans:
        for word in span.text.split():
            if word:
                tok = _Token(
                    word=word, bold=span.bold, italic=span.italic,
                    src_strike=span.strikethrough, underline=span.underline,
                )
                parts.append(tok.render() + ' ')
    return ''.join(parts).rstrip()


def _render_highlighted(block: TextBlock, bg: str, diff_strike: bool = False) -> str:
    parts = []
    for span in block.spans:
        for word in span.text.split():
            if word:
                tok = _Token(
                    word=word, bold=span.bold, italic=span.italic,
                    src_strike=span.strikethrough, underline=span.underline,
                )
                parts.append(tok.render(bg=bg, diff_strike=diff_strike) + ' ')
    return ''.join(parts).rstrip()


def _word_diff_html(old_block: TextBlock, new_block: TextBlock) -> Tuple[str, str, str]:
    """
    Word-level diff within a matched block pair.
    Returns (old_html, new_html, change_type) where
    change_type is 'equal' | 'modified' | 'emphasis'.
    """
    old_tok = _block_tokens(old_block)
    new_tok = _block_tokens(new_block)

    matcher = difflib.SequenceMatcher(
        None,
        [t.word for t in old_tok],
        [t.word for t in new_tok],
        autojunk=False,
    )

    old_parts: List[str] = []
    new_parts: List[str] = []
    has_content_change = False
    has_emphasis_change = False

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for oi, ni in zip(range(i1, i2), range(j1, j2)):
                ot, nt = old_tok[oi], new_tok[ni]
                if ot.fmt_key != nt.fmt_key:
                    has_emphasis_change = True
                    old_parts.append(ot.render(bg=BG_EMPHASIS) + ' ')
                    new_parts.append(nt.render(bg=BG_EMPHASIS) + ' ')
                else:
                    old_parts.append(ot.render() + ' ')
                    new_parts.append(nt.render() + ' ')

        elif tag == 'delete':
            has_content_change = True
            for tok in old_tok[i1:i2]:
                old_parts.append(tok.render(bg=BG_DELETE, diff_strike=True) + ' ')

        elif tag == 'insert':
            has_content_change = True
            for tok in new_tok[j1:j2]:
                new_parts.append(tok.render(bg=BG_INSERT) + ' ')

        elif tag == 'replace':
            has_content_change = True
            for tok in old_tok[i1:i2]:
                old_parts.append(tok.render(bg=BG_MOD_OLD, diff_strike=True) + ' ')
            for tok in new_tok[j1:j2]:
                new_parts.append(tok.render(bg=BG_MOD_NEW) + ' ')

    change_type = 'equal'
    if has_content_change:
        change_type = 'modified'
    elif has_emphasis_change:
        change_type = 'emphasis'

    return ''.join(old_parts).rstrip(), ''.join(new_parts).rstrip(), change_type


def _truncate(text: str, limit: int = 120) -> str:
    return (text[:limit] + '…') if len(text) > limit else text


def _sidebar_item(kind: str, label: str, old_txt: str, new_txt: str, cid: str) -> str:
    badge_map = {
        'del':  ('bdel',  'Deleted'),
        'add':  ('badd',  'Added'),
        'mod':  ('bmod',  'Modified'),
        'emph': ('bemph', 'Emphasis'),
    }
    bclass, blabel = badge_map.get(kind, ('bmod', label))
    oe = _html.escape(_truncate(old_txt))
    ne = _html.escape(_truncate(new_txt))

    if old_txt and new_txt:
        detail = (
            f'<div style="margin-top:3px;font-size:11px">'
            f'<span style="text-decoration:line-through;color:#f38ba8">{oe}</span>'
            f' <span style="color:#89b4fa">→</span> '
            f'<span style="color:#a6e3a1">{ne}</span>'
            f'</div>'
        )
    elif old_txt:
        detail = (
            f'<div style="margin-top:3px;font-size:11px;'
            f'text-decoration:line-through;color:#f38ba8">{oe}</div>'
        )
    else:
        detail = (
            f'<div style="margin-top:3px;font-size:11px;color:#a6e3a1">{ne}</div>'
        )

    return (
        f'<div class="ch {kind}">'
        f'<a href="#{cid}" style="text-decoration:none;color:inherit;display:block">'
        f'<span class="badge {bclass}">{blabel}</span>'
        f'{detail}'
        f'</a>'
        f'</div>'
    )


def _p(inner: str, anchor: str = '') -> str:
    a_tag = f'<a name="{anchor}"></a>' if anchor else ''
    return f'<p style="margin:3px 0;line-height:1.6">{a_tag}{inner}</p>\n'


# ── Main diff function ───────────────────────────────────────────────────────
def build_diff_html(old_doc: Document, new_doc: Document) -> Tuple[str, str, str]:
    """
    Two-pass diff:
      Pass 1 — block-level SequenceMatcher aligns paragraphs.
      Pass 2 — word-level diff within each 'replace' pair to find
               content modifications and emphasis-only changes.

    Returns (old_panel_html, new_panel_html, sidebar_html).
    """
    old_blocks = old_doc.blocks
    new_blocks = new_doc.blocks

    # Match on whitespace-normalized text so that PDF-extraction whitespace
    # noise (non-breaking spaces, double spaces) does not create false changes.
    old_plain = [_norm(b.plain_text()) for b in old_blocks]
    new_plain = [_norm(b.plain_text()) for b in new_blocks]

    block_matcher = difflib.SequenceMatcher(None, old_plain, new_plain, autojunk=False)

    old_parts: List[str] = []
    new_parts: List[str] = []
    sidebar_items: List[str] = []
    change_num = 0
    stats = {'added': 0, 'deleted': 0, 'modified': 0, 'emphasis': 0}

    for tag, i1, i2, j1, j2 in block_matcher.get_opcodes():

        if tag == 'equal':
            for bi, bj in zip(range(i1, i2), range(j1, j2)):
                ob = old_blocks[bi]
                nb = new_blocks[bj]
                wold, wnew, ctype = _word_diff_html(ob, nb)
                if ctype == 'equal':
                    old_parts.append(_p(_render_plain(ob)))
                    new_parts.append(_p(_render_plain(nb)))
                else:
                    # Formatting differs despite identical text
                    change_num += 1
                    cid = f'c{change_num}'
                    old_parts.append(_p(wold, cid))
                    new_parts.append(_p(wnew, cid))
                    old_txt = ob.plain_text().strip()
                    new_txt = nb.plain_text().strip()
                    if ctype == 'emphasis':
                        stats['emphasis'] += 1
                        sidebar_items.append(_sidebar_item('emph', 'Emphasis', old_txt, new_txt, cid))
                    else:
                        stats['modified'] += 1
                        sidebar_items.append(_sidebar_item('mod', 'Modified', old_txt, new_txt, cid))

        elif tag == 'delete':
            for b in old_blocks[i1:i2]:
                txt = b.plain_text().strip()
                if not txt:
                    continue
                change_num += 1
                cid = f'c{change_num}'
                old_parts.append(_p(_render_highlighted(b, BG_DELETE, diff_strike=True), cid))
                stats['deleted'] += 1
                sidebar_items.append(_sidebar_item('del', 'Deleted', txt, '', cid))

        elif tag == 'insert':
            for b in new_blocks[j1:j2]:
                txt = b.plain_text().strip()
                if not txt:
                    continue
                change_num += 1
                cid = f'c{change_num}'
                new_parts.append(_p(_render_highlighted(b, BG_INSERT), cid))
                stats['added'] += 1
                sidebar_items.append(_sidebar_item('add', 'Added', '', txt, cid))

        elif tag == 'replace':
            # Pair paragraphs by similarity rather than position so that
            # shifted / revoked / inserted items are not mispaired.
            for op, ob, nb in _align_replace(old_blocks[i1:i2], new_blocks[j1:j2]):

                if op == 'pair':
                    old_txt = ob.plain_text().strip()
                    new_txt = nb.plain_text().strip()
                    if not old_txt and not new_txt:
                        continue

                    wold, wnew, ctype = _word_diff_html(ob, nb)
                    if ctype == 'equal':
                        old_parts.append(_p(wold or _render_plain(ob)))
                        new_parts.append(_p(wnew or _render_plain(nb)))
                    else:
                        change_num += 1
                        cid = f'c{change_num}'
                        old_parts.append(_p(wold, cid))
                        new_parts.append(_p(wnew, cid))
                        if ctype == 'emphasis':
                            stats['emphasis'] += 1
                            sidebar_items.append(_sidebar_item('emph', 'Emphasis', old_txt, new_txt, cid))
                        else:
                            stats['modified'] += 1
                            sidebar_items.append(_sidebar_item('mod', 'Modified', old_txt, new_txt, cid))

                elif op == 'del':
                    txt = ob.plain_text().strip()
                    if not txt:
                        continue
                    change_num += 1
                    cid = f'c{change_num}'
                    old_parts.append(_p(_render_highlighted(ob, BG_DELETE, diff_strike=True), cid))
                    stats['deleted'] += 1
                    sidebar_items.append(_sidebar_item('del', 'Deleted', txt, '', cid))

                else:  # 'add'
                    txt = nb.plain_text().strip()
                    if not txt:
                        continue
                    change_num += 1
                    cid = f'c{change_num}'
                    new_parts.append(_p(_render_highlighted(nb, BG_INSERT), cid))
                    stats['added'] += 1
                    sidebar_items.append(_sidebar_item('add', 'Added', '', txt, cid))

    sidebar_html = _build_sidebar(sidebar_items, stats)
    return ''.join(old_parts), ''.join(new_parts), sidebar_html


def _build_sidebar(items: List[str], stats: dict) -> str:
    total = sum(stats.values())
    css = """<style>
      body { font-family:Arial,sans-serif; font-size:12px;
             background:#1e1e2e; color:#cdd6f4; margin:0; padding:8px; }
      .header { font-size:13px; font-weight:bold; color:#cba6f7;
                margin-bottom:4px; padding-bottom:6px;
                border-bottom:1px solid #45475a; }
      .stats  { font-size:11px; margin-bottom:8px; line-height:2; }
      .stat   { display:inline-block; padding:1px 7px; border-radius:3px;
                margin-right:4px; font-weight:bold; }
      .s-del  { background:#f38ba8; color:#1e1e2e; }
      .s-add  { background:#a6e3a1; color:#1e1e2e; }
      .s-mod  { background:#ffd699; color:#1e1e2e; }
      .s-emph { background:#cba6f7; color:#1e1e2e; }
      .ch     { margin:4px 0; padding:6px 8px; border-radius:5px;
                background:#313244; cursor:pointer; }
      .ch:hover { background:#3d3f5a; }
      .del    { border-left:3px solid #f38ba8; }
      .add    { border-left:3px solid #a6e3a1; }
      .mod    { border-left:3px solid #ffd699; }
      .emph   { border-left:3px solid #cba6f7; }
      .badge  { display:inline-block; font-size:10px; font-weight:bold;
                padding:1px 6px; border-radius:3px; margin-right:6px;
                vertical-align:middle; }
      .bdel   { background:#f38ba8; color:#1e1e2e; }
      .badd   { background:#a6e3a1; color:#1e1e2e; }
      .bmod   { background:#ffd699; color:#1e1e2e; }
      .bemph  { background:#cba6f7; color:#1e1e2e; }
      .empty  { color:#585b70; font-style:italic; text-align:center;
                margin-top:40px; }
      a { text-decoration:none; color:inherit; }
    </style>"""

    if not items:
        return css + '<body><div class="empty">No changes detected.</div></body>'

    header = (
        f'<div class="header">Changes '
        f'<span style="font-weight:normal;font-size:11px;color:#a6adc8">'
        f'({total} total)</span></div>'
    )
    stats_html = (
        f'<div class="stats">'
        f'<span class="stat s-del">{stats["deleted"]} Deleted</span>'
        f'<span class="stat s-add">{stats["added"]} Added</span>'
        f'<span class="stat s-mod">{stats["modified"]} Modified</span>'
        f'<span class="stat s-emph">{stats["emphasis"]} Emphasis</span>'
        f'</div>'
    )
    return css + '<body>' + header + stats_html + '\n'.join(items) + '</body>'
