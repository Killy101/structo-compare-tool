import fitz  # pymupdf
from models.document import Document, TextBlock, TextSpan


def extract_pdf(path: str) -> Document:
    doc = Document()
    pdf = fitz.open(path)

    for page in pdf:
        # Collect StrikeOut annotation rects on this page
        strike_rects = [
            annot.rect for annot in page.annots()
            if annot.type[1] == 'StrikeOut'
        ]

        raw = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for raw_block in raw['blocks']:
            if raw_block.get('type') != 0:
                continue  # skip image blocks

            block = TextBlock()
            for line in raw_block['lines']:
                for span_data in line['spans']:
                    flags = span_data['flags']
                    bold = bool(flags & 16)   # bit 4
                    italic = bool(flags & 2)  # bit 1

                    span_rect = fitz.Rect(span_data['bbox'])
                    # Drawn strikethrough: check annotation overlap
                    strikethrough = any(span_rect.intersects(r) for r in strike_rects)

                    text = span_data['text']
                    if text:
                        block.spans.append(TextSpan(
                            text=text,
                            bold=bold,
                            italic=italic,
                            strikethrough=strikethrough,
                        ))
                # Newline at end of each line
                block.spans.append(TextSpan(text=' '))

            if any(s.text.strip() for s in block.spans):
                doc.blocks.append(block)

    pdf.close()
    return doc
