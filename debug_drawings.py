"""
Run: python debug_drawings.py path/to/file.pdf
Shows what kind of drawing items PyMuPDF finds so we can verify
strikethrough/underline detection paths.
"""
import sys
import fitz

path = sys.argv[1] if len(sys.argv) > 1 else None
if not path:
    print("Usage: python debug_drawings.py file.pdf")
    sys.exit(1)

pdf = fitz.open(path)
for page_num, page in enumerate(pdf):
    drawings = page.get_drawings()
    if not drawings:
        continue
    print(f"\n=== Page {page_num + 1}: {len(drawings)} drawing path(s) ===")
    for pi, path_obj in enumerate(drawings[:30]):   # show first 30 paths
        items = path_obj.get('items', [])
        for item in items:
            kind = item[0]
            if kind == 'l':
                p1, p2 = item[1], item[2]
                dy = abs(p1.y - p2.y)
                print(f"  path[{pi}] LINE  y1={p1.y:.1f} y2={p2.y:.1f} dy={dy:.2f}  "
                      f"x: {min(p1.x,p2.x):.1f}–{max(p1.x,p2.x):.1f}")
            elif kind == 're':
                r = item[1]
                print(f"  path[{pi}] RECT  y: {r.y0:.1f}–{r.y1:.1f} h={r.height:.2f}  "
                      f"x: {r.x0:.1f}–{r.x1:.1f}  "
                      f"{'<-- thin rule' if r.height <= 4 else ''}")
            else:
                print(f"  path[{pi}] {kind.upper()}")

    # Show first page with any thin rects
    thin = [
        item for p in drawings for item in p.get('items', [])
        if item[0] == 're' and item[1].height <= 4
    ]
    lines = [
        item for p in drawings for item in p.get('items', [])
        if item[0] == 'l' and abs(item[1].y - item[2].y) <= 2
    ]
    print(f"  => Thin rects (h<=4): {len(thin)}   Horizontal lines: {len(lines)}")

    annotations = list(page.annots())
    strike_annots = [a for a in annotations if a.type[1] == 'StrikeOut']
    underline_annots = [a for a in annotations if a.type[1] == 'Underline']
    if strike_annots or underline_annots:
        print(f"  => StrikeOut annotations: {len(strike_annots)}  Underline: {len(underline_annots)}")

pdf.close()
