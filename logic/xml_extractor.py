from lxml import etree
from models.document import Document, TextBlock, TextSpan
from typing import List


BOLD_TAGS = {'b', 'strong', 'bold'}
ITALIC_TAGS = {'i', 'em', 'italic'}
STRIKE_TAGS = {'s', 'del', 'strike', 'strikethrough'}
BLOCK_TAGS = {'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
              'section', 'article', 'blockquote', 'pre'}

# Word XML run-property tags (w: namespace)
WORD_BOLD_TAGS = {'b', 'bcs'}
WORD_ITALIC_TAGS = {'i', 'ics'}
WORD_STRIKE_TAGS = {'strike', 'dstrike'}


def _local(tag) -> str:
    if not isinstance(tag, str):
        return ''
    return tag.split('}')[-1].lower() if '}' in tag else tag.lower()


def _has_style(el, prop: str) -> bool:
    style = el.get('style', '')
    return prop in style


def extract_xml(path: str) -> Document:
    doc = Document()

    with open(path, 'rb') as f:
        raw = f.read()

    doc.raw_xml = raw.decode('utf-8', errors='replace')

    try:
        tree = etree.fromstring(raw)
    except etree.XMLSyntaxError:
        doc.blocks.append(TextBlock(spans=[TextSpan(text=doc.raw_xml)]))
        return doc

    blocks: List[TextBlock] = [TextBlock()]

    def process(el, bold=False, italic=False, strike=False):
        tag = _local(el.tag)

        # Resolve emphasis from tag name
        is_bold = bold or tag in BOLD_TAGS or (tag in WORD_BOLD_TAGS)
        is_italic = italic or tag in ITALIC_TAGS or (tag in WORD_ITALIC_TAGS)
        is_strike = strike or tag in STRIKE_TAGS or (tag in WORD_STRIKE_TAGS)

        # Resolve emphasis from style attribute
        if _has_style(el, 'font-weight:bold') or _has_style(el, 'font-weight: bold'):
            is_bold = True
        if _has_style(el, 'font-style:italic') or _has_style(el, 'font-style: italic'):
            is_italic = True
        if _has_style(el, 'line-through'):
            is_strike = True

        # Block-level elements start a new paragraph
        if tag in BLOCK_TAGS:
            if blocks[-1].spans:
                blocks.append(TextBlock())

        # Append element's own text to current block
        if el.text and el.text.strip():
            blocks[-1].spans.append(TextSpan(
                text=el.text,
                bold=is_bold,
                italic=is_italic,
                strikethrough=is_strike,
            ))

        # Recurse into children
        for child in el:
            process(child, is_bold, is_italic, is_strike)
            # tail text belongs to parent context (not child's emphasis)
            if child.tail and child.tail.strip():
                blocks[-1].spans.append(TextSpan(
                    text=child.tail,
                    bold=bold,
                    italic=italic,
                    strikethrough=strike,
                ))

        # Close block-level elements
        if tag in BLOCK_TAGS and blocks[-1].spans:
            blocks.append(TextBlock())

    process(tree)
    doc.blocks = [b for b in blocks if b.spans]
    return doc
