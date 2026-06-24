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
                  anchors: dict, highlight_mode: str) -> str:
    """Render *blocks*, highlighting words whose flat index is flagged in
    *changed* and emitting a navigation anchor where *anchors* has one.

    *highlight_mode* is ``"del"`` or ``"add"``, driving both word-level
    foreground colour and the paragraph background band.

    The word iteration order here is identical to :func:`_flatten`, so the
    running global index ``g`` stays aligned with ``changed`` / ``anchors``.
    """
    para_bg = "#fff8f0" if highlight_mode == "del" else "#f0fff8"

    out: List[str] = []
    g = 0
    for block in blocks:
        if block.is_blank():
            out.append(_p(""))
            continue
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
    return "".join(out)


# -----------------------------------------------------------------------
# Sidebar helpers
# -----------------------------------------------------------------------
def _truncate(text: str, limit: int = 120) -> str:
    return (text[:limit] + "…") if len(text) > limit else text


def _sidebar_item(kind: str, label: str, old_txt: str, new_txt: str, cid: str) -> str:
    """Render a single entry for the changes‑sidebar.

    ``kind`` is one of ``del`` / ``add`` / ``mod`` and drives the colour and
    the anchor fragment used for navigation.
    """
    badge_map = {
        "del": ("bdel", "Deleted"),
        "add": ("badd", "Added"),
        "mod": ("bmod", "Modified"),
    }
    bclass, blabel = badge_map.get(kind, ("bmod", label))
    oe = _html.escape(_truncate(old_txt))
    ne = _html.escape(_truncate(new_txt))

    if old_txt and new_txt:
        detail = (
            f'<div style="margin-top:3px;font-size:11px">'
            f'<span style="text-decoration:line-through;color:#f38ba8">{oe}</span>'
            f' <span style="color:#89b4fa">→</span> '
            f'<span style="color:#a6e3a1">{ne}</span>'
            f"</div>"
        )
    elif old_txt:
        detail = f'<div style="margin-top:3px;font-size:11px;text-decoration:line-through;color:#f38ba8">{oe}</div>'
    else:
        detail = f'<div style="margin-top:3px;font-size:11px;color:#a6e3a1">{ne}</div>'

    href = f"#{kind}:{cid}"
    return (
        f'<div class="ch {kind}">'
        f'<a href="{href}" style="text-decoration:none;color:inherit;display:block">'
        f'<span class="badge {bclass}">{blabel}</span>'
        f"{detail}"
        f"</a>"
        f"</div>"
    )


# -----------------------------------------------------------------------
# Main diff entry point
# -----------------------------------------------------------------------
def build_diff_html(old_doc: Document, new_doc: Document) -> Tuple[str, str, str, list]:
    """
    Flat word‑stream diff.

    Returns ``(old_html, new_html, sidebar_html, changes)`` where ``changes``
    is an ordered list of ``{"id", "kind", "old", "new"}`` dicts used for
    change‑to‑change navigation.
    """
    old_blocks = old_doc.blocks
    new_blocks = new_doc.blocks

    old_words = _flatten(old_blocks)
    new_words = _flatten(new_blocks)

    matcher = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)

    old_changed = [False] * len(old_words)
    new_changed = [False] * len(new_words)
    old_anchors: dict = {}
    new_anchors: dict = {}

    sidebar_items: List[str] = []
    changes: List[dict] = []
    stats = {"added": 0, "deleted": 0, "modified": 0}
    cnum = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        cnum += 1
        cid = f"c{cnum}"
        for k in range(i1, i2):
            old_changed[k] = True
        for k in range(j1, j2):
            new_changed[k] = True

        old_txt = " ".join(old_words[i1:i2])
        new_txt = " ".join(new_words[j1:j2])

        if tag == "insert":
            kind = "add"
            stats["added"] += 1
            new_anchors[j1] = cid
            sidebar_items.append(_sidebar_item("add", "Added", "", new_txt, cid))
        elif tag == "delete":
            kind = "del"
            stats["deleted"] += 1
            old_anchors[i1] = cid
            sidebar_items.append(_sidebar_item("del", "Deleted", old_txt, "", cid))
        else:  # replace -> modification (paired delete + insert)
            kind = "mod"
            stats["modified"] += 1
            old_anchors[i1] = cid
            new_anchors[j1] = cid
            sidebar_items.append(_sidebar_item("mod", "Modified", old_txt, new_txt, cid))

        changes.append({"id": cid, "kind": kind, "old": old_txt, "new": new_txt})

    old_html = _render_panel(old_blocks, old_changed, old_anchors, "del")
    new_html = _render_panel(new_blocks, new_changed, new_anchors, "add")
    sidebar_html = _build_sidebar(sidebar_items, stats)
    return old_html, new_html, sidebar_html, changes


# -----------------------------------------------------------------------
# Sidebar builder
# -----------------------------------------------------------------------
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
      .ch     { margin:4px 0; padding:6px 8px; border-radius:5px;
                background:#313244; cursor:pointer; }
      .ch:hover { background:#3d3f5a; }
      .del    { border-left:3px solid #f38ba8; }
      .add    { border-left:3px solid #a6e3a1; }
      .mod    { border-left:3px solid #ffd699; }
      .badge  { display:inline-block; font-size:10px; font-weight:bold;
                padding:1px 6px; border-radius:3px; margin-right:6px;
                vertical-align:middle; }
      .bdel   { background:#f38ba8; color:#1e1e2e; }
      .badd   { background:#a6e3a1; color:#1e1e2e; }
      .bmod   { background:#ffd699; color:#1e1e2e; }
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
        f"</div>"
    )
    return css + "<body>" + header + stats_html + "\n".join(items) + "</body>"
