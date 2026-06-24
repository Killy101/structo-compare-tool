from unittest.mock import patch

from logic.pdf_extractor import extract_pdf


class _DummyPage:
    def annots(self):
        return []

    def get_links(self):
        return []

    def get_drawings(self):
        return []

    def get_text(self, mode, flags=None):
        return {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {
                                    "text": "Hello world",
                                    "flags": 0,
                                }
                            ]
                        }
                    ],
                }
            ]
        }


class _DummyPdf:
    def __init__(self, page):
        self._page = page

    def __iter__(self):
        yield self._page

    def close(self):
        return None


def test_extract_pdf_handles_spans_without_bbox():
    with patch("logic.pdf_extractor.fitz") as mock_fitz:
        mock_fitz.TEXT_PRESERVE_WHITESPACE = 0
        mock_fitz.open.return_value = _DummyPdf(_DummyPage())

        doc = extract_pdf("dummy.pdf")

    assert len(doc.blocks) == 1
    assert doc.blocks[0].plain_text() == "Hello world"


class _WrappedPage:
    """A page whose single paragraph is soft-wrapped across three lines."""
    def __init__(self, lines):
        self._lines = lines

    def annots(self):
        return []

    def get_links(self):
        return []

    def get_drawings(self):
        return []

    def get_text(self, mode, flags=None):
        return {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "bbox": [50, 50 + 14 * i, 400, 64 + 14 * i],
                            "spans": [{
                                "text": text,
                                "flags": 0,
                                "size": 11,
                                "bbox": [50, 50 + 14 * i, 400, 64 + 14 * i],
                            }],
                        }
                        for i, text in enumerate(self._lines)
                    ],
                }
            ]
        }


def test_wrapped_lines_merge_into_one_paragraph_block():
    """Soft-wrapped lines in one PyMuPDF block must collapse to one block so
    that reflowed text does not generate false diffs."""
    with patch("logic.pdf_extractor.fitz") as mock_fitz:
        mock_fitz.TEXT_PRESERVE_WHITESPACE = 0
        mock_fitz.Rect = lambda *a: None          # bbox not needed here
        mock_fitz.open.return_value = _DummyPdf(
            _WrappedPage(["the quick brown", "fox jumps over", "the lazy dog"])
        )
        doc = extract_pdf("dummy.pdf")

    assert len(doc.blocks) == 1
    assert doc.blocks[0].plain_text() == "the quick brown fox jumps over the lazy dog"
