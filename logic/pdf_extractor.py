# logic/pdf_extractor.py
"""
PDF -> our internal ``Document`` model.

*   Uses **PyMuPDF** (``fitz``) to pull text + basic styling.
*   Detects **bold / italic** from both the PDF flags and the font name.
*   Detects **underline / strikethrough** from:
        -  PDF annotations (StrikeOut / Underline)
        -  Link annotations (visual underline but encoded as a link)
        -  Very thin drawing objects (lines / rectangles) that Word
           emits for those decorations.
*   Reconstructs document **structure** -- one block per visual line,
    indentation from x-position, blank blocks for paragraph / page gaps,
    and a coarse ``kind`` (heading / list / normal) -- so the editable
    panels mirror the original layout.
"""

import bisect
import re
import time
import fitz                               # pip install pymupdf
from models.document import Document, TextBlock, TextSpan
from typing import Any, List, Tuple

# A leading list marker: bullet glyphs, "1." / "1)" / "a." / "iv." etc.
_LIST_RE = re.compile(r'^\s*([•‣●▪◦⁃∙o\-\*]|'
                      r'(\d+|[a-zA-Z]|[ivxlcdmIVXLCDM]+)[.)])\s+')


def _build_thin_line_index(
    drawings: List[dict],
) -> Tuple[List[Tuple[float, float, float]], List[float]]:
    """Pre-process page drawings into a sorted spatial index.

    Extracts only the thin horizontal rules (vector lines and thin
    filled rectangles ≤ 4 px tall) that underline / strikethrough
    detection needs, discarding everything else up front.

    Returns ``(items, y_keys)`` where *items* is a list of
    ``(y_center, x0, x1)`` tuples sorted by *y_center* and *y_keys*
    is the pre-extracted list of y values for fast ``bisect`` lookups.
    Doing this **once per page** instead of inside the per-span loop
    reduces the inner-loop cost from O(all_drawing_items) to
    O(log n + matching_lines) — roughly a 30-100× speedup on
    documents with many drawing objects.
    """
    items: List[Tuple[float, float, float]] = []
    for path in drawings:
        for item in path.get("items", []):
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) <= 2:          # horizontal only
                    y = (p1.y + p2.y) / 2
                    items.append((y, min(p1.x, p2.x), max(p1.x, p2.x)))
            elif kind == "re":
                r = item[1]
                if r.height <= 4:                   # thin rule only
                    items.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
    items.sort()
    return items, [t[0] for t in items]


def _check_line_overlap(
    span_rect: fitz.Rect,
    items: List[Tuple[float, float, float]],
    y_keys: List[float],
    mid_y_frac: float,
    tolerance_frac: float,
) -> bool:
    """Return ``True`` if any pre-indexed thin rule overlaps *span_rect*
    at the given vertical fraction.

    Uses the sorted ``items`` / ``y_keys`` built by
    :func:`_build_thin_line_index` so only the rules in the matching
    y-band are inspected (binary search on ``y_keys``).
    """
    if not items:
        return False
    span_h = span_rect.y1 - span_rect.y0
    if span_h <= 0:
        return False

    target_y = span_rect.y0 + span_h * mid_y_frac
    tol      = span_h * tolerance_frac
    y_lo     = target_y - tol
    y_hi     = target_y + tol

    lo = bisect.bisect_left(y_keys, y_lo)
    for i in range(lo, len(items)):
        y, x0, x1 = items[i]
        if y > y_hi:
            break
        if x0 <= span_rect.x1 and x1 >= span_rect.x0:
            return True
    return False


def extract_pdf(path: str) -> Document:
    """
    Turn a PDF file into a :class:`models.document.Document`.

    The function is deliberately *pure* - it never creates Qt objects,
    which means it is safe to run inside a ``QThread``.
    """
    doc = Document()
    pdf = fitz.open(path)

    for page_num, page in enumerate(pdf):
        # Yield the GIL every 10 pages so the main-thread event loop stays
        # responsive even when processing very large documents.
        if page_num and page_num % 10 == 0:
            time.sleep(0)
        # -------------------------------------------------------------
        # 1. Annotation-based detection (StrikeOut / Underline)
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
        # Hyperlink rects — spans that fall under a link annotation are NOT
        # treated as underlined emphasis (they are styled by the browser/viewer,
        # not by the author for semantic emphasis).
        try:
            link_rects = [fitz.Rect(lk['from']) for lk in page.get_links() if lk.get('from')]
        except Exception:
            link_rects = []

        # -------------------------------------------------------------
        # 2. Drawing-based detection (thin lines / rectangles)
        # -------------------------------------------------------------
        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []
        _thin_items, _thin_y_keys = _build_thin_line_index(drawings)

        # -------------------------------------------------------------
        # 3. Extract the raw text + per-span metadata
        # -------------------------------------------------------------
        # ``get_text("dict", ...)`` returns a nested dict at runtime, but the
        # PyMuPDF stub types it as ``str``; annotate as Any so the type
        # checker doesn't flag the dict indexing / .get() calls below.
        raw: Any = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        # Work out the page's left text margin and the dominant body font
        # size so we can reconstruct indentation and detect headings.
        x_starts: List[float] = []
        sizes: List[float] = []
        for rb in raw["blocks"]:
            if rb.get("type") != 0:
                continue
            for ln in rb["lines"]:
                for sp in ln["spans"]:
                    if sp.get("text", "").strip():
                        bb = sp.get("bbox")
                        if bb:
                            x_starts.append(bb[0])
                        if sp.get("size"):
                            sizes.append(round(sp["size"], 1))
        page_left = min(x_starts) if x_starts else 0.0
        body_size = max(set(sizes), key=sizes.count) if sizes else 11.0
        # One indent "unit" ~ half an em of the body font.
        unit = max(body_size * 0.5, 4.0)

        # A blank block separates this page's content from the previous one.
        if doc.blocks and not doc.blocks[-1].is_blank():
            doc.blocks.append(TextBlock(kind='blank'))

        prev_bottom = None

        for raw_block in raw["blocks"]:
            if raw_block.get("type") != 0:          # ignore images, etc.
                continue

            # Soft-wrapped lines inside one PyMuPDF block belong to the *same*
            # paragraph; we merge them into a single TextBlock so that diffing
            # happens at the paragraph level.  (Splitting per visual line makes
            # the diff explode with false positives whenever the two documents
            # wrap the same paragraph at different points.)
            block_spans: List[TextSpan] = []
            first_line_spans: List[TextSpan] = []
            first_x0 = None
            first_size = body_size
            block_top = None
            block_bottom = None

            for line in raw_block["lines"]:
                line_spans: List[TextSpan] = []
                line_size = body_size

                for span_data in line["spans"]:
                    # --------------------- styling flags -----------------
                    flags = span_data["flags"]
                    font_name = span_data.get("font", "").lower()
                    if span_data.get("size"):
                        line_size = span_data["size"]

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
                    # Underline / strike detection - draw-based part
                    # -------------------------------------------------
                    draw_underline = False
                    draw_strike = False
                    if span_rect is not None:
                        # Underline zone - roughly the baseline (~85% of span height)
                        draw_underline = _check_line_overlap(
                            span_rect, _thin_items, _thin_y_keys, mid_y_frac=0.87, tolerance_frac=0.20
                        )
                        # Strikethrough zone - middle of the glyphs (~45% of span height)
                        draw_strike = _check_line_overlap(
                            span_rect, _thin_items, _thin_y_keys, mid_y_frac=0.45, tolerance_frac=0.25
                        )
                        # Overlap resolution - if both flags fire we prefer underline.
                        if draw_strike and draw_underline:
                            draw_strike = False

                    # -------------------------------------------------
                    # Annotation-based detection
                    # -------------------------------------------------
                    strike = False
                    underline = False
                    if span_rect is not None:
                        strike = (
                            any(span_rect.intersects(r) for r in strike_rects)
                            or draw_strike
                        )
                        # Suppress underline on hyperlink spans — the underline
                        # is rendered by the viewer, not authored as emphasis.
                        is_link = any(span_rect.intersects(lr) for lr in link_rects)
                        underline = (not is_link) and (
                            any(span_rect.intersects(r) for r in underline_rects)
                            or draw_underline
                        )

                    text = span_data["text"]
                    if text:                               # keep empty spans out
                        line_spans.append(
                            TextSpan(
                                text=text,
                                bold=bold,
                                italic=italic,
                                strikethrough=strike,
                                underline=underline,
                            )
                        )

                # Discard whitespace-only lines.
                if not any(s.text.strip() for s in line_spans):
                    continue

                # ---- geometry of this visual line --------------------
                lbbox = line.get("bbox")
                lx0 = lbbox[0] if lbbox else page_left
                ltop = lbbox[1] if lbbox else (prev_bottom or 0.0)
                lbottom = lbbox[3] if lbbox else ltop

                if first_x0 is None:                 # first line of the paragraph
                    first_x0 = lx0
                    first_size = line_size
                    first_line_spans = line_spans
                    block_top = ltop
                else:                                # join with a single space
                    block_spans.append(TextSpan(text=" "))
                block_spans.extend(line_spans)
                block_bottom = lbottom

            # Skip empty paragraphs.
            if not any(s.text.strip() for s in block_spans):
                continue

            # Insert a blank block when there is a clear vertical gap before this
            # paragraph - this preserves paragraph / section spacing.
            if (prev_bottom is not None and block_top is not None
                    and (block_top - prev_bottom) > first_size * 0.9):
                if doc.blocks and not doc.blocks[-1].is_blank():
                    doc.blocks.append(TextBlock(kind='blank'))

            indent = max(0, round((first_x0 - page_left) / unit)) if first_x0 else 0

            # ---- structural role (judged from the first line) ----------
            block_text = ' '.join(s.text for s in block_spans).strip()
            first_text = ' '.join(s.text for s in first_line_spans).strip()
            kind = 'normal'
            if _LIST_RE.match(first_text):
                kind = 'list'
            elif (first_size >= body_size * 1.15
                  and all(s.bold for s in first_line_spans)
                  and len(block_text) < 120):
                kind = 'heading'

            doc.blocks.append(
                TextBlock(spans=block_spans, indent=indent, kind=kind)
            )
            if block_bottom is not None:
                prev_bottom = block_bottom

    # Trim a trailing blank block, if any.
    while doc.blocks and doc.blocks[-1].is_blank():
        doc.blocks.pop()

    pdf.close()
    return doc


_render_cache: dict = {}   # (path, zoom_key) -> html string


def render_pdf_preview(path: str, zoom: float = 2.0, max_pages: int = 80) -> str:
    """
    Render the first ``max_pages`` pages of *path* as PNG data-URIs and wrap them
    in a small HTML fragment.  Used by the "PDF Page View" toggle so the user can
    see the **real layout** of the source file.  ``zoom`` is the render scale
    (higher = sharper but heavier); the UI drives it via zoom controls.

    Results are cached by (path, rounded-zoom) so repeated zoom requests at the
    same level reuse previously rendered pages without re-opening the PDF.
    """
    import base64
    # Round zoom to 1 decimal place for cache keying (0.5, 0.6, … 4.0)
    zoom_key = round(zoom, 1)
    cache_key = (path, zoom_key)
    if cache_key in _render_cache:
        return _render_cache[cache_key]

    pdf = fitz.open(path)

    n_pages = min(len(pdf), max_pages)
    # Clamp the render scale to keep memory in check on very long documents.
    zoom = max(0.5, min(zoom, 4.0))
    if n_pages > 40:
        zoom = min(zoom, 1.6)

    mat = fitz.Matrix(zoom, zoom)

    parts = [
        '<div style="background:#525659;padding:14px 0;font-family:Arial,sans-serif;">'
    ]
    for i in range(n_pages):
        page = pdf[i]
        pix = page.get_pixmap(matrix=mat, alpha=False)
        b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
        parts.append(
            f'<div style="text-align:center;margin-bottom:18px;">'
            f'<p style="color:#cbd5e1;font-size:10px;margin:0 0 6px">Page {i+1} of {n_pages}</p>'
            f'<img src="data:image/png;base64,{b64}" '
            f'style="max-width:98%;background:#fff;'
            f'border:2px solid #1e293b;" />'
            f"</div>"
        )
    if len(pdf) > max_pages:
        parts.append(
            f'<p style="color:#fbbf24;text-align:center;font-size:12px;">'
            f'Showing first {max_pages} of {len(pdf)} pages.</p>'
        )
    pdf.close()
    parts.append("</div>")
    html = "".join(parts)

    # Cache the result (evict oldest if cache grows too large)
    if len(_render_cache) >= 20:
        _render_cache.pop(next(iter(_render_cache)))
    _render_cache[cache_key] = html
    return html


def clear_render_cache():
    """Discard all cached PDF preview renders (e.g. when loading new files)."""
    _render_cache.clear()
