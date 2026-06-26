# logic/differ.py
"""
Word‑stream diff for ``Document`` objects.

Change detection runs on a **flat stream of words** spanning the whole
document, *independent of paragraph / line boundaries*.  This is the key to
accuracy: PDF line wrapping and paragraph segmentation are layout artifacts,
not content, and they routinely differ between two versions of the same file.
A block‑level diff mistakes those layout shifts for content changes and emits
large numbers of false "modified" / "deleted" / "added" paragraphs.  Diffing
the flat word stream makes reflow and re‑segmentation invisible, so only real
word‑level edits remain.

The detected changes are then rendered back onto each document's paragraph
structure: changed words in the old panel are highlighted red, changed words
in the new panel green, and a paired delete+insert is reported as a single
"modified" entry (orange) in the change list.

``build_diff_html`` returns ``(old_html, new_html, sidebar_html, changes)``.
"""
import difflib
import html as _html
from dataclasses import dataclass
from typing import Iterator, List, Tuple

from models.document import Document, TextBlock, TextSpan


# -----------------------------------------------------------------------
# Token – a single word together with its source formatting.
# -----------------------------------------------------------------------
@dataclass
class _Token:
    word: str
    bold: bool = False
    italic: bool = False
    src_strike: bool = False
    underline: bool = False

    def render(self, highlight: str = "") -> str:
        """Render the token as a ``<span>`` with the appropriate CSS.

        *highlight* is ``""`` (unchanged), ``"del"`` (removed), or ``"add"`` (inserted).
        Source-level strikethrough is preserved; diff decoration is foreground colour only.
        """
        t = _html.escape(self.word)
        styles: List[str] = []
        decorations: List[str] = []

        if self.bold:
            styles.append("font-weight:bold")
        if self.italic:
            styles.append("font-style:italic")
        if self.underline:
            decorations.append("underline")
        if self.src_strike:
            decorations.append("line-through")
            if not highlight:
                styles.append("color:#888")

        if decorations:
            styles.append("text-decoration:" + " ".join(decorations))

        if highlight == "del":
            styles.append("color:#c0392b")       # red foreground
            styles.append("background:#ffeaea")  # very light pink tint
            styles.append("border-radius:3px")
            styles.append("padding:0 2px")
        elif highlight == "add":
            styles.append("color:#1a7a3c")       # dark green foreground
            styles.append("background:#eafaf1")  # very light green tint
            styles.append("border-radius:3px")
            styles.append("padding:0 2px")

        if styles:
            return f'<span style="{";".join(styles)}">{t}</span>'
        return t


# -----------------------------------------------------------------------
# Flatten a document into a word stream.
# -----------------------------------------------------------------------
def _block_words(block: TextBlock) -> Iterator[Tuple[str, TextSpan]]:
    """Yield ``(word, span)`` pairs for every word in a block, in order."""
    for span in block.spans:
        for word in span.text.split():
            if word:
                yield word, span


def _flatten(blocks: List[TextBlock]) -> List[str]:
    """Return the document's words as a flat list (blank blocks skipped)."""
    words: List[str] = []
    for block in blocks:
        if block.is_blank():
            continue
        for word, _span in _block_words(block):
            words.append(word)
    return words


def _flatten_tokens(blocks: List[TextBlock]) -> List[_Token]:
    """Return a _Token per word, parallel to :func:`_flatten` (blank blocks skipped)."""
    tokens: List[_Token] = []
    for block in blocks:
        if block.is_blank():
            continue
        for word, span in _block_words(block):
            tokens.append(_Token(
                word=word,
                bold=span.bold,
                italic=span.italic,
                src_strike=span.strikethrough,
                underline=span.underline,
            ))
    return tokens


def _render_toks(toks: List[_Token], limit: int = 120) -> str:
    """Render tokens as HTML with their emphasis, truncated at *limit* chars."""
    parts: List[str] = []
    chars = 0
    for tok in toks:
        if chars > limit:
            parts.append('…')
            break
        chars += len(tok.word) + 1
        t = _html.escape(tok.word)
        styles: List[str] = []
        decos: List[str] = []
        if tok.bold:
            styles.append('font-weight:bold')
        if tok.italic:
            styles.append('font-style:italic')
        if tok.underline:
            decos.append('underline')
        if tok.src_strike:
            decos.append('line-through')
        if decos:
            styles.append('text-decoration:' + ' '.join(decos))
        if styles:
            parts.append(f'<span style="{";".join(styles)}">{t}</span>')
        else:
            parts.append(t)
    return ' '.join(parts)


# -----------------------------------------------------------------------
# Alignment spacer helpers
# -----------------------------------------------------------------------
_LH  = 22   # line-height px (13 px font × 1.65 leading, rounded up)
_PM  = 9    # per-paragraph margin px (4 top + 4 bottom + 1 gap)
_CPL = 75   # estimated chars per line (panel ≈ 600 px @ 13 px Arial)


def _block_h(block: TextBlock) -> int:
    if block.is_blank():
        return _LH + _PM
    n = max(1, (len(block.plain_text()) + _CPL - 1) // _CPL)
    return n * _LH + _PM


def _compute_spacers(
    old_blocks: List[TextBlock],
    new_blocks: List[TextBlock],
    matcher: 'difflib.SequenceMatcher',
) -> Tuple[dict, dict]:
    """Return (old_spacers, new_spacers) mapping block_index → extra px after that block.

    Index -1 means "before block 0".
    """
    old_sp: dict = {}
    new_sp: dict = {}

    def _add(d: dict, k: int, v: int) -> None:
        d[k] = d.get(k, 0) + v

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for oi, ni in zip(range(i1, i2), range(j1, j2)):
                diff = _block_h(old_blocks[oi]) - _block_h(new_blocks[ni])
                if diff > 0:
                    _add(new_sp, ni, diff)
                elif diff < 0:
                    _add(old_sp, oi, -diff)

        elif tag == 'replace':
            old_h = sum(_block_h(old_blocks[i]) for i in range(i1, i2))
            new_h = sum(_block_h(new_blocks[j]) for j in range(j1, j2))
            diff = old_h - new_h
            if diff > 0:
                _add(new_sp, (j2 - 1) if j2 > j1 else j1 - 1, diff)
            elif diff < 0:
                _add(old_sp, (i2 - 1) if i2 > i1 else i1 - 1, -diff)

        elif tag == 'delete':      # only in old → gap in new
            total = sum(_block_h(old_blocks[i]) for i in range(i1, i2))
            _add(new_sp, j1 - 1, total)

        elif tag == 'insert':      # only in new → gap in old
            total = sum(_block_h(new_blocks[j]) for j in range(j1, j2))
            _add(old_sp, i1 - 1, total)

    return old_sp, new_sp


# -----------------------------------------------------------------------
# Render one panel, highlighting changed words and dropping nav anchors.
# -----------------------------------------------------------------------
def _p(inner: str, indent: int = 0, bg: str = "") -> str:
    """Wrap *inner* in a paragraph, reproducing the source indentation with
    non‑breaking spaces (the panels normalise these back when re‑extracting).

    *bg* is an optional paragraph-level background band colour rendered when
    the paragraph contains at least one changed word.
    """
    pad = "&nbsp;" * indent if indent else ""
    style = "margin:3px 0;line-height:1.6"
    if bg:
        style += f";background:{bg};padding:2px 6px;border-radius:3px"
    return f'<p style="{style}">{pad}{inner}</p>\n'


def _render_panel(blocks: List[TextBlock], changed: List[bool],
                  anchors: dict, highlight_mode: str,
                  spacers: 'dict | None' = None) -> str:
    """Render *blocks*, highlighting words whose flat index is flagged in
    *changed* and emitting a navigation anchor where *anchors* has one.

    *highlight_mode* is ``"del"`` or ``"add"``, driving both word-level
    foreground colour and the paragraph background band.

    *spacers* maps block_index → extra px to add after that block, with -1
    meaning "before block 0".  This keeps equal blocks vertically aligned.

    The word iteration order here is identical to :func:`_flatten`, so the
    running global index ``g`` stays aligned with ``changed`` / ``anchors``.
    """
    para_bg = "#fff8f0" if highlight_mode == "del" else "#f0fff8"

    out: List[str] = []
    g = 0

    if spacers:
        px = spacers.get(-1, 0)
        if px > 0:
            out.append(f'<div style="height:{px}px"></div>\n')

    for idx, block in enumerate(blocks):
        if block.is_blank():
            out.append(_p(""))
        else:
            pieces: List[str] = []
            block_has_change = False
            for word, span in _block_words(block):
                tok = _Token(
                    word=word,
                    bold=span.bold,
                    italic=span.italic,
                    src_strike=span.strikethrough,
                    underline=span.underline,
                )
                word_changed = changed[g]
                if word_changed:
                    block_has_change = True
                cid = anchors.get(g)
                a_tag = f'<a name="{cid}">&#8203;</a>' if cid else ""
                pieces.append(a_tag + tok.render(highlight=highlight_mode if word_changed else ""))
                g += 1
            out.append(_p(" ".join(pieces), indent=block.indent,
                          bg=para_bg if block_has_change else ""))

        if spacers:
            px = spacers.get(idx, 0)
            if px > 0:
                out.append(f'<div style="height:{px}px"></div>\n')

    return "".join(out)


# -----------------------------------------------------------------------
# Sidebar helpers
# -----------------------------------------------------------------------
def _sidebar_item(kind: str, label: str,
                  old_toks: List[_Token], new_toks: List[_Token], cid: str) -> str:
    """Render a single entry for the changes‑sidebar.

    ``kind`` is one of ``del`` / ``add`` / ``mod``.  Tokens carry their source
    emphasis (bold/italic/underline/strike) so the sidebar reflects the actual
    formatting of the changed text.  Emphasis-indicator chips are shown next to
    the badge when the relevant tokens carry formatting.
    """
    badge_map = {
        "del": ("bdel", "Deleted"),
        "add": ("badd", "Added"),
        "mod": ("bmod", "Modified"),
    }
    bclass, blabel = badge_map.get(kind, ("bmod", label))

    # For "del", the emphasis of the removed text matters; for "add"/"mod",
    # the emphasis of the incoming (new) text is what the user needs to see.
    emph_src = old_toks if kind == "del" else new_toks
    chip = ('font-size:9px;padding:0 4px;border-radius:2px;'
            'background:#ddd6fe;color:#4c1d95;margin-left:3px;vertical-align:middle')
    emph_chips = ''
    if any(t.bold for t in emph_src):
        emph_chips += f'<span style="{chip};font-weight:bold">B</span>'
    if any(t.italic for t in emph_src):
        emph_chips += f'<span style="{chip};font-style:italic">I</span>'
    if any(t.underline for t in emph_src):
        emph_chips += f'<span style="{chip};text-decoration:underline">U</span>'
    if any(t.src_strike for t in emph_src):
        emph_chips += f'<span style="{chip};text-decoration:line-through">S</span>'

    old_rendered = _render_toks(old_toks)
    new_rendered = _render_toks(new_toks)

    if old_toks and new_toks:
        detail = (
            f'<div style="margin-top:3px;font-size:11px">'
            f'<span style="text-decoration:line-through;color:#ef4444">{old_rendered}</span>'
            f' <span style="color:#6366f1">→</span> '
            f'<span style="color:#16a34a">{new_rendered}</span>'
            f'</div>'
        )
    elif old_toks:
        detail = f'<div style="margin-top:3px;font-size:11px;color:#ef4444">{old_rendered}</div>'
    else:
        detail = f'<div style="margin-top:3px;font-size:11px;color:#16a34a">{new_rendered}</div>'

    href = f"#{kind}:{cid}"
    return (
        f'<div class="ch {kind}">'
        f'<a href="{href}" style="text-decoration:none;color:inherit;display:block">'
        f'<span class="badge {bclass}">{blabel}</span>{emph_chips}'
        f'{detail}'
        f'</a>'
        f'</div>'
    )


# -----------------------------------------------------------------------
# Two-level diff helpers
# -----------------------------------------------------------------------
def _block_text(block: TextBlock) -> str:
    """Canonical text of a block for coarse block-level hashing."""
    if block.is_blank():
        return ''
    return ' '.join(w for w, _ in _block_words(block))


def _compute_block_word_spans(blocks: List[TextBlock]) -> List[Tuple[int, int]]:
    """Return (word_start, word_end) for each block.

    Blank blocks contribute zero words; their span is (pos, pos).
    Indices are aligned with the flat list produced by :func:`_flatten`.
    """
    spans: List[Tuple[int, int]] = []
    pos = 0
    for block in blocks:
        if block.is_blank():
            spans.append((pos, pos))
        else:
            count = sum(1 for _ in _block_words(block))
            spans.append((pos, pos + count))
            pos += count
    return spans


# -----------------------------------------------------------------------
# Main diff entry point
# -----------------------------------------------------------------------
def build_diff_html(old_doc: Document, new_doc: Document) -> Tuple[str, str, str, list]:
    """
    Two-level word-stream diff.

    1. A **block-level** SequenceMatcher identifies equal vs. changed paragraph
       ranges in O(n_blocks²) — fast even for 300-page legal documents.
    2. A **word-level** SequenceMatcher then runs *only* on the changed paragraph
       ranges, so the expensive O(n_words²) cost is proportional to the size of
       the *differences* rather than the whole document.

    Returns ``(old_html, new_html, sidebar_html, changes)`` where ``changes``
    is an ordered list of ``{"id", "kind", "old", "new"}`` dicts used for
    change-to-change navigation.
    """
    old_blocks = old_doc.blocks
    new_blocks = new_doc.blocks

    # Pre-compute word-position spans for every block (needed for index mapping).
    old_spans = _compute_block_word_spans(old_blocks)
    new_spans = _compute_block_word_spans(new_blocks)

    # Flat word lists — needed for the word-level sub-diffs.
    old_words  = _flatten(old_blocks)
    new_words  = _flatten(new_blocks)
    # Parallel token lists carry per-word emphasis for sidebar rendering.
    old_tokens = _flatten_tokens(old_blocks)
    new_tokens = _flatten_tokens(new_blocks)

    old_changed = [False] * len(old_words)
    new_changed = [False] * len(new_words)
    old_anchors: dict = {}
    new_anchors: dict = {}

    sidebar_items: List[str] = []
    changes: List[dict] = []
    stats = {"added": 0, "deleted": 0, "modified": 0}
    cnum = 0

    # Level-1: block-level diff.
    # autojunk=False is accurate for small/medium docs; for very large ones
    # (>4 000 blocks total) the O(n²) cost becomes prohibitive, so we fall
    # back to autojunk=True which treats frequently-repeated paragraphs as
    # "junk" and skips them — much faster with only minor accuracy loss.
    old_hashes = [_block_text(b) for b in old_blocks]
    new_hashes = [_block_text(b) for b in new_blocks]
    _large_doc  = (len(old_hashes) + len(new_hashes)) > 4_000
    block_matcher = difflib.SequenceMatcher(
        None, old_hashes, new_hashes, autojunk=_large_doc)

    for btag, oi1, oi2, ni1, ni2 in block_matcher.get_opcodes():
        if btag == "equal":
            continue

        # Word range covered by the changed old blocks
        if oi1 < oi2:
            ow_lo, ow_hi = old_spans[oi1][0], old_spans[oi2 - 1][1]
        else:
            ow_lo = ow_hi = old_spans[oi1][0] if oi1 < len(old_spans) else len(old_words)

        # Word range covered by the changed new blocks
        if ni1 < ni2:
            nw_lo, nw_hi = new_spans[ni1][0], new_spans[ni2 - 1][1]
        else:
            nw_lo = nw_hi = new_spans[ni1][0] if ni1 < len(new_spans) else len(new_words)

        sub_old      = old_words[ow_lo:ow_hi]
        sub_new      = new_words[nw_lo:nw_hi]
        sub_old_toks = old_tokens[ow_lo:ow_hi]
        sub_new_toks = new_tokens[nw_lo:nw_hi]

        # Level-2: word-level diff within the changed block range
        use_autojunk = len(sub_old) > 5_000 or len(sub_new) > 5_000
        word_matcher = difflib.SequenceMatcher(None, sub_old, sub_new, autojunk=use_autojunk)

        for wtag, wi1, wi2, wj1, wj2 in word_matcher.get_opcodes():
            if wtag == "equal":
                continue

            cnum += 1
            cid = f"c{cnum}"

            abs_i1, abs_i2 = ow_lo + wi1, ow_lo + wi2
            abs_j1, abs_j2 = nw_lo + wj1, nw_lo + wj2

            for k in range(abs_i1, abs_i2):
                old_changed[k] = True
            for k in range(abs_j1, abs_j2):
                new_changed[k] = True

            old_txt = " ".join(sub_old[wi1:wi2])
            new_txt = " ".join(sub_new[wj1:wj2])

            if wtag == "insert":
                kind = "add"
                stats["added"] += 1
                new_anchors[abs_j1] = cid
                sidebar_items.append(_sidebar_item(
                    "add", "Added", [], sub_new_toks[wj1:wj2], cid))
            elif wtag == "delete":
                kind = "del"
                stats["deleted"] += 1
                old_anchors[abs_i1] = cid
                sidebar_items.append(_sidebar_item(
                    "del", "Deleted", sub_old_toks[wi1:wi2], [], cid))
            else:  # replace → modification (paired delete + insert)
                kind = "mod"
                stats["modified"] += 1
                old_anchors[abs_i1] = cid
                new_anchors[abs_j1] = cid
                sidebar_items.append(_sidebar_item(
                    "mod", "Modified", sub_old_toks[wi1:wi2], sub_new_toks[wj1:wj2], cid))

            changes.append({"id": cid, "kind": kind, "old": old_txt, "new": new_txt})

    old_sp, new_sp = _compute_spacers(old_blocks, new_blocks, block_matcher)
    old_html = _render_panel(old_blocks, old_changed, old_anchors, "del", spacers=old_sp)
    new_html = _render_panel(new_blocks, new_changed, new_anchors, "add", spacers=new_sp)
    sidebar_html = _build_sidebar(sidebar_items, stats)
    return old_html, new_html, sidebar_html, changes


# -----------------------------------------------------------------------
# Live alignment (no diff highlights) — used while the user is editing
# -----------------------------------------------------------------------
def align_documents_html(old_doc: Document, new_doc: Document) -> Tuple[str, str]:
    """Render both documents with vertical spacers so matching blocks sit at
    the same position.  No diff highlights — used during live editing."""
    old_blocks = old_doc.blocks
    new_blocks = new_doc.blocks

    old_texts = [_block_text(b) for b in old_blocks]
    new_texts = [_block_text(b) for b in new_blocks]
    _large = (len(old_texts) + len(new_texts)) > 4_000
    sm = difflib.SequenceMatcher(None, old_texts, new_texts, autojunk=_large)
    old_sp, new_sp = _compute_spacers(old_blocks, new_blocks, sm)

    def _render(blocks: List[TextBlock], spacers: dict) -> str:
        out: List[str] = []
        px0 = spacers.get(-1, 0)
        if px0 > 0:
            out.append(f'<div style="height:{px0}px"></div>\n')
        for idx, block in enumerate(blocks):
            if block.is_blank():
                out.append('<p style="margin:3px 0;line-height:1.6"></p>\n')
            else:
                pad = '&nbsp;' * block.indent if block.indent else ''
                inner = pad + block.to_html()
                out.append(f'<p style="margin:3px 0;line-height:1.6">{inner}</p>\n')
            px = spacers.get(idx, 0)
            if px > 0:
                out.append(f'<div style="height:{px}px"></div>\n')
        return ''.join(out)

    return _render(old_blocks, old_sp), _render(new_blocks, new_sp)


# -----------------------------------------------------------------------
# Sidebar builder
# -----------------------------------------------------------------------
def _build_sidebar(items: List[str], stats: dict) -> str:
    total = sum(stats.values())
    css = """<style>
      body { font-family:Arial,sans-serif; font-size:12px;
             background:#ffffff; color:#1e293b; margin:0; padding:8px; }
      .header { font-size:13px; font-weight:bold; color:#4f46e5;
                margin-bottom:4px; padding-bottom:6px;
                border-bottom:1px solid #e2e8f0; }
      .stats  { font-size:11px; margin-bottom:8px; line-height:2; }
      .stat   { display:inline-block; padding:1px 7px; border-radius:3px;
                margin-right:4px; font-weight:bold; }
      .s-del  { background:#fecaca; color:#991b1b; }
      .s-add  { background:#bbf7d0; color:#166534; }
      .s-mod  { background:#fde68a; color:#92400e; }
      .ch     { margin:4px 0; padding:6px 8px; border-radius:5px;
                background:#f8fafc; border:1px solid #e2e8f0; cursor:pointer; }
      .ch:hover { background:#f1f5f9; }
      .del    { border-left:3px solid #ef4444; }
      .add    { border-left:3px solid #22c55e; }
      .mod    { border-left:3px solid #f59e0b; }
      .badge  { display:inline-block; font-size:10px; font-weight:bold;
                padding:1px 6px; border-radius:3px; margin-right:6px;
                vertical-align:middle; }
      .bdel   { background:#fecaca; color:#991b1b; }
      .badd   { background:#bbf7d0; color:#166534; }
      .bmod   { background:#fde68a; color:#92400e; }
      .empty  { color:#94a3b8; font-style:italic; text-align:center;
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
        f"</div>"
    )
    return css + "<body>" + header + stats_html + "\n".join(items) + "</body>"
