# logic/text_parser.py
"""Parse edited panel text back into a :class:`Document`.

Kept Qt-free so it can be unit-tested in isolation and reused anywhere.
"""
from models.document import Document, TextBlock, TextSpan


def text_to_doc(text: str) -> Document:
    """Convert edited panel text into a Document.

    Each line becomes a block; blank lines are preserved as blank blocks so
    paragraph spacing survives a re-compare, and leading whitespace is mapped
    to the block's ``indent`` level (round-tripping the diff view's padding).
    Non-breaking spaces (used for indent padding in the diff HTML) are first
    normalised back to ordinary spaces.
    """
    doc = Document()
    for raw_line in text.replace('\xa0', ' ').split('\n'):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            doc.blocks.append(TextBlock(kind='blank'))
            continue
        indent = len(line) - len(line.lstrip(' '))
        doc.blocks.append(TextBlock(spans=[TextSpan(text=stripped)], indent=indent))
    # Drop a trailing blank block so a stray final newline doesn't skew alignment.
    while doc.blocks and doc.blocks[-1].is_blank():
        doc.blocks.pop()
    return doc
