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


def render_pdf_preview(path: str, zoom: float = 1.4, max_pages: int = 60) -> str:
    """
    Render each PDF page to a PNG image and return an HTML string with the
    images embedded as data-URIs.  Used by the 'PDF Page View' toggle so
    users see the true page layout rather than extracted text.

    zoom=1.4 gives ~96 dpi equivalent for a letter/A4 page — sharp enough
    to read but small enough that QTextBrowser handles it without lag.
    Reduces to 1.0 automatically for documents with more than 30 pages.
    """
    import base64
    pdf = fitz.open(path)
    n = min(len(pdf), max_pages)
    # Drop resolution a bit for long documents to avoid memory pressure
    if n > 30:
        zoom = min(zoom, 1.0)
    mat = fitz.Matrix(zoom, zoom)

    parts = [
        '<div style="background:#505050;padding:12px 16px;'
        'font-family:Arial,sans-serif;">'
    ]
    for i in range(n):
        page = pdf[i]
        pix  = page.get_pixmap(matrix=mat, alpha=False)
        b64  = base64.b64encode(pix.tobytes('png')).decode('ascii')
        parts.append(
            f'<div style="text-align:center;margin-bottom:18px;">'
            f'<p style="color:#aaa;font-size:10px;margin:0 0 5px">Page {i + 1} of {n}</p>'
            f'<img src="data:image/png;base64,{b64}" '
            f'style="max-width:100%;'
            f'box-shadow:0 3px 10px rgba(0,0,0,0.55);'
            f'border:1px solid #333;" />'
            f'</div>'
        )
    if len(pdf) > max_pages:
        parts.append(
            f'<p style="color:#f9e2af;text-align:center;font-size:12px;">'
            f'Showing first {max_pages} of {len(pdf)} pages.</p>'
        )
    pdf.close()
    parts.append('</div>')
    return ''.join(parts)
