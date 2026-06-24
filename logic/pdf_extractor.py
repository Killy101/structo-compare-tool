# logic/pdf_extractor.py
"""
PDF → our internal ``Document`` model.

*   Uses **PyMuPDF** (``fitz``) to pull text + basic styling.
*   Detects **bold / italic** from both the PDF flags and the font name.
*   Detects **underline / strikethrough** from:
        –  PDF annotations (StrikeOut / Underline)
        –  Link annotations (visual underline but encoded as a link)
        –  Very thin drawing objects (lines / rectangles) that Word
           emits for those decorations.
*   Normalises whitespace – the diff stage later collapses any remaining
   “double‑space” noise, which eliminates a huge class of false positives.
"""

import fitz                               # pip install pymupdf
from models.document import Document, TextBlock, TextSpan
from typing import List


def _check_line_overlap(
    span_rect: fitz.Rect,
    drawings: List[dict],
    mid_y_frac: float,
    tolerance_frac: float,
) -> bool:
    """
    Return ``True`` if *any* thin horizontal drawing (line OR thin rectangle)
    intersects the span at the given vertical fraction.

    ``mid_y_frac``  –  where inside the span we look (0 = top, 1 = bottom).  
    ``tolerance_frac`` –  how far up/down we are willing to wander,
    expressed as a fraction of the span height.
    """
    span_h = span_rect.y1 - span_rect.y0
    if span_h <= 0:
        return False

    target_y = span_rect.y0 + span_h * mid_y_frac
    tol = span_h * tolerance_frac

    for path in drawings:
        for item in path.get("items", []):
            kind = item[0]

            # -------------------------------------------------------------
            # Vector line – the usual PDF “draw line” object
            # -------------------------------------------------------------
            if kind == "l":
                p1, p2 = item[1], item[2]
                # Discard non‑horizontal lines (angle > ~2 px)
                if abs(p1.y - p2.y) > 2:
                    continue
                line_y = (p1.y + p2.y) / 2
                if abs(line_y - target_y) > tol:
                    continue
                if min(p1.x, p2.x) <= span_rect.x1 and max(p1.x, p2.x) >= span_rect.x0:
                    return True

            # -------------------------------------------------------------
            # Filled rectangle – how Word encodes a thin rule.
            # -------------------------------------------------------------
            elif kind == "re":
                rect = item[1]
                # Anything taller than ~4 px is definitely not a rule.
                if rect.height > 4:
                    continue
                rect_mid_y = (rect.y0 + rect.y1) / 2
                if abs(rect_mid_y - target_y) > tol:
                    continue
                if rect.x0 <= span_rect.x1 and rect.x1 >= span_rect.x0:
                    return True
    return False


def extract_pdf(path: str) -> Document:
    """
    Turn a PDF file into a :class:`models.document.Document`.

    The function is deliberately *pure* – it never creates Qt objects,
    which means it is safe to run inside a ``QThread``.
    """
    doc = Document()
    pdf = fitz.open(path)

    for page in pdf:
        # -------------------------------------------------------------
        # 1️⃣  Annotation‑based detection (StrikeOut / Underline)
        # -------------------------------------------------------------
        strike_rects = [
            annot.rect
            for annot in page.annots()
            if annot.type[1] == "StrikeOut"
        ]
        underline_rects = [
            annot.rect
            for annot in page.annots()
            if annot.type[1] == "Underline"
        ]

        # Hyperlink annotations are visually underlined but are stored
        # as Link annotations – we treat them as “underline”.
        try:
            link_rects = [fitz.Rect(lk["from"]) for lk in page.get_links()]
        except Exception:
            link_rects = []

        # -------------------------------------------------------------
        # 2️⃣  Drawing‑based detection (thin lines / rectangles)
        # -------------------------------------------------------------
        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []

        # -------------------------------------------------------------
        # 3️⃣  Extract the raw text + per‑span metadata
        # -------------------------------------------------------------
        raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        for raw_block in raw["blocks"]:
            if raw_block.get("type") != 0:          # ignore images, etc.
                continue

            block = TextBlock()

            for line in raw_block["lines"]:
                for span_data in line["spans"]:
                    # --------------------- styling flags -----------------
                    flags = span_data["flags"]
                    font_name = span_data.get("font", "").lower()

                    bold = (
                        bool(flags & 16)
                        or "bold" in font_name
                        or "black" in font_name
                        or "heavy" in font_name
                        or "semibold" in font_name
                    )
                    italic = (
                        bool(flags & 2)
                        or "italic" in font_name
                        or "oblique" in font_name
                    )

                    # ------------------- geometry ------------------------
                    bbox = span_data.get("bbox")
                    if bbox is None:
                        span_rect = None
                    else:
                        try:
                            span_rect = fitz.Rect(bbox)
                        except Exception:
                            span_rect = None

                    # -------------------------------------------------
                    # Underline / strike detection – draw‑based part
                    # -------------------------------------------------
                    draw_underline = False
                    draw_strike = False
                    if span_rect is not None:
                        # Underline zone – roughly the baseline (~85 % of span height)
                        draw_underline = _check_line_overlap(
                            span_rect, drawings, mid_y_frac=0.87, tolerance_frac=0.20
                        )
                        # Strikethrough zone – middle of the glyphs (~45 % of span height)
                        draw_strike = _check_line_overlap(
                            span_rect, drawings, mid_y_frac=0.45, tolerance_frac=0.25
                        )
                        # Overlap resolution – if both flags fire we prefer underline.
                        if draw_strike and draw_underline:
                            draw_strike = False

                    # -------------------------------------------------
                    # Annotation‑based detection
                    # -------------------------------------------------
                    strike = False
                    underline = False
                    if span_rect is not None:
                        strike = (
                            any(span_rect.intersects(r) for r in strike_rects)
                            or draw_strike
                        )
                        underline = (
                            any(span_rect.intersects(r) for r in underline_rects)
                            or any(span_rect.intersects(r) for r in link_rects)
                            or draw_underline
                        )

                    text = span_data["text"]
                    if text:                               # keep empty spans out
                        block.spans.append(
                            TextSpan(
                                text=text,
                                bold=bold,
                                italic=italic,
                                strikethrough=strike,
                                underline=underline,
                            )
                        )
                # Insert a *single* space between the original PDF lines.
                # (PDF text extraction often leaves the line break out of the
                # span list, so we add it manually.)
                block.spans.append(TextSpan(text=" "))

            # Discard empty blocks – they only contain whitespace.
            if any(s.text.strip() for s in block.spans):
                doc.blocks.append(block)

    pdf.close()
    return doc


def render_pdf_preview(path: str, zoom: float = 1.4, max_pages: int = 60) -> str:
    """
    Render the first ``max_pages`` pages of *path* as PNG data‑URIs and wrap them
    in a very small HTML fragment.  The fragment is used by the “PDF Page View”
    toggle so the user can see the **real layout** of the source file.
    """
    import base64
    pdf = fitz.open(path)

    n_pages = min(len(pdf), max_pages)
    # If the document is huge we back‑off the resolution to keep memory low.
    if n_pages > 30:
        zoom = min(zoom, 1.0)

    mat = fitz.Matrix(zoom, zoom)

    parts = [
        '<div style="background:#505050;padding:12px 16px;font-family:Arial,sans-serif;">'
    ]
    for i in range(n_pages):
        page = pdf[i]
        pix = page.get_pixmap(matrix=mat, alpha=False)
        b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
        parts.append(
            f'<div style="text-align:center;margin-bottom:18px;">'
            f'<p style="color:#aaa;font-size:10px;margin:0 0 5px">Page {i+1} of {n_pages}</p>'
            f'<img src="data:image/png;base64,{b64}" '
            f'style="max-width:100%;box-shadow:0 3px 10px rgba(0,0,0,0.55);border:1px solid #333;" />'
            f"</div>"
        )
    if len(pdf) > max_pages:
        parts.append(
            f'<p style="color:#f9e2af;text-align:center;font-size:12px;">'
            f'Showing first {max_pages} of {len(pdf)} pages.</p>'
        )
    pdf.close()
    parts.append("</div>")
    return "".join(parts)