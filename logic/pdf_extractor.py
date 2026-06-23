import fitz  # pymupdf
from models.document import Document, TextBlock, TextSpan


def _check_line_overlap(span_rect, drawings, mid_y_frac: float, tolerance_frac: float) -> bool:
    """
    Check if any drawn horizontal mark (line or thin filled rectangle) intersects
    the span at the given vertical fraction.  Word-generated PDFs often encode
    strikethrough / underline as a very thin filled rectangle ('re' item) rather
    than a vector line ('l' item).
    """
    span_h = span_rect.y1 - span_rect.y0
    if span_h <= 0:
        return False
    target_y = span_rect.y0 + span_h * mid_y_frac
    tol = span_h * tolerance_frac

    for path in drawings:
        for item in path.get('items', []):
            kind = item[0]

            if kind == 'l':
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) > 2:
                    continue
                line_y = (p1.y + p2.y) / 2
                if abs(line_y - target_y) > tol:
                    continue
                if min(p1.x, p2.x) <= span_rect.x1 and max(p1.x, p2.x) >= span_rect.x0:
                    return True

            elif kind == 're':
                # Thin horizontal rectangle used as a rule (strikethrough or underline)
                rect = item[1]
                if rect.height > 4:          # too tall to be a rule
                    continue
                rect_mid_y = (rect.y0 + rect.y1) / 2
                if abs(rect_mid_y - target_y) > tol:
                    continue
                if rect.x0 <= span_rect.x1 and rect.x1 >= span_rect.x0:
                    return True

    return False


def extract_pdf(path: str) -> Document:
    doc = Document()
    pdf = fitz.open(path)

    for page in pdf:
        # Annotation-based strikethrough rects
        strike_rects = [
            annot.rect for annot in page.annots()
            if annot.type[1] == 'StrikeOut'
        ]
        underline_rects = [
            annot.rect for annot in page.annots()
            if annot.type[1] == 'Underline'
        ]

        # Drawing-based detection
        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []

        raw = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for raw_block in raw['blocks']:
            if raw_block.get('type') != 0:
                continue

            block = TextBlock()
            for line in raw_block['lines']:
                for span_data in line['spans']:
                    flags = span_data['flags']
                    font = span_data.get('font', '').lower()
                    # Bold/italic may be encoded via the flag bits OR the font name
                    # (e.g. "TimesNewRomanPS-BoldMT", "Calibri-Italic").
                    bold = (
                        bool(flags & 16)
                        or 'bold' in font or 'black' in font or 'heavy' in font
                        or 'semibold' in font
                    )
                    italic = (
                        bool(flags & 2)
                        or 'italic' in font or 'oblique' in font
                    )

                    span_rect = fitz.Rect(span_data['bbox'])

                    # Strikethrough: annotation-based OR drawn horizontal line at mid-height
                    strikethrough = (
                        any(span_rect.intersects(r) for r in strike_rects)
                        or _check_line_overlap(span_rect, drawings, mid_y_frac=0.5, tolerance_frac=0.4)
                    )

                    # Underline: annotation-based OR drawn horizontal line near bottom
                    underline = (
                        any(span_rect.intersects(r) for r in underline_rects)
                        or _check_line_overlap(span_rect, drawings, mid_y_frac=0.9, tolerance_frac=0.25)
                    )

                    text = span_data['text']
                    if text:
                        block.spans.append(TextSpan(
                            text=text,
                            bold=bold,
                            italic=italic,
                            strikethrough=strikethrough,
                            underline=underline,
                        ))
                block.spans.append(TextSpan(text=' '))

            if any(s.text.strip() for s in block.spans):
                doc.blocks.append(block)

    pdf.close()
    return doc
