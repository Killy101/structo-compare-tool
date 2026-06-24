# logic/xml_extractor.py
"""
Turn an XML (or HTML) source file into the same ``Document`` model that the
PDF extractor produces.

*   Handles both the *semantic* tags (b, i, s, etc.) **and** the Word
    namespace tags (w:b, w:i, w:strike, …).
*   Detects inline ``style`` attributes that set ``font-weight``,
    ``font-style`` or ``text-decoration``.
*   Normalises tag names to lower‑case, strips namespaces and treats any
    unknown element as plain text – the diff engine will then ignore it.
"""

from lxml import etree
from models.document import Document, TextBlock, TextSpan
from typing import List


# -----------------------------------------------------------------------
# Tag / style helpers
# -----------------------------------------------------------------------
BOLD_TAGS = {"b", "strong", "bold"}
ITALIC_TAGS = {"i", "em", "italic"}
STRIKE_TAGS = {"s", "del", "strike", "strikethrough"}
BLOCK_TAGS = {
    "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "blockquote", "pre",
}

# Word‑specific run‑property tags (they live in the ``w:`` namespace)
WORD_BOLD_TAGS = {"b", "bcs"}
WORD_ITALIC_TAGS = {"i", "ics"}
WORD_STRIKE_TAGS = {"strike", "dstrike"}


def _local(tag: str) -> str:
    """Strip namespace and lower‑case a tag name."""
    if not isinstance(tag, str):
        return ""
    return tag.split("}")[-1].lower() if "}" in tag else tag.lower()


def _has_style(el: etree._Element, prop: str) -> bool:
    """Return True if the element's ``style`` attribute contains *prop*."""
    return prop in el.get("style", "")


# -----------------------------------------------------------------------
# Main extractor
# -----------------------------------------------------------------------
def extract_xml(path: str) -> Document:
    doc = Document()

    # Preserve the raw source for the “XML editor” tab.
    with open(path, "rb") as f:
        raw = f.read()
    doc.raw_xml = raw.decode("utf-8", errors="replace")

    # -------------------------------------------------------------------
    # Try to parse – if it fails we just dump the raw text as a single block.
    # -------------------------------------------------------------------
    try:
        tree = etree.fromstring(raw)
    except etree.XMLSyntaxError:
        doc.blocks.append(TextBlock(spans=[TextSpan(text=doc.raw_xml)]))
        return doc

    # -------------------------------------------------------------------
    # Walk the tree, carrying the current emphasis state down the recursion.
    # -------------------------------------------------------------------
    blocks: List[TextBlock] = [TextBlock()]          # start with an empty block

    def _process(el: etree._Element, bold=False, italic=False, strike=False):
        tag = _local(el.tag)

        # ---- Resolve emphasis from *tag name* -------------------------
        is_bold = bold or tag in BOLD_TAGS or tag in WORD_BOLD_TAGS
        is_italic = italic or tag in ITALIC_TAGS or tag in WORD_ITALIC_TAGS
        is_strike = strike or tag in STRIKE_TAGS or tag in WORD_STRIKE_TAGS

        # ---- Resolve emphasis from the ``style`` attribute ------------
        if _has_style(el, "font-weight:bold") or _has_style(el, "font-weight: bold"):
            is_bold = True
        if _has_style(el, "font-style:italic") or _has_style(el, "font-style: italic"):
            is_italic = True
        if _has_style(el, "line-through"):
            is_strike = True

        # ---- Block‑level tags start a *new* paragraph -----------------
        if tag in BLOCK_TAGS:
            # If the current block already has content, start a fresh one.
            if blocks[-1].spans:
                blocks.append(TextBlock())

        # ---- Element's own text (before its children) -----------------
        if el.text and el.text.strip():
            blocks[-1].spans.append(
                TextSpan(
                    text=el.text,
                    bold=is_bold,
                    italic=is_italic,
                    strikethrough=is_strike,
                )
            )

        # ---- Recurse into children ------------------------------------
        for child in el:
            _process(child, is_bold, is_italic, is_strike)

            # The child's ``tail`` belongs to the *parent* context.
            if child.tail and child.tail.strip():
                blocks[-1].spans.append(
                    TextSpan(
                        text=child.tail,
                        bold=bold,
                        italic=italic,
                        strikethrough=strike,
                    )
                )

        # ---- Closing a block element – start a new paragraph ----------
        if tag in BLOCK_TAGS and blocks[-1].spans:
            blocks.append(TextBlock())

    _process(tree)

    # Remove any completely empty trailing block that may have been added.
    doc.blocks = [b for b in blocks if b.spans]
    return doc