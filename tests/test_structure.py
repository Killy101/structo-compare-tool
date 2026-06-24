"""Tests for structure-preserving extraction, diff, and edit round-trip."""
from models.document import Document, TextBlock, TextSpan
from logic.differ import build_diff_html


def _doc(lines):
    """Build a Document from (indent, text) tuples; '' text => blank block."""
    d = Document()
    for indent, text in lines:
        if not text:
            d.blocks.append(TextBlock(kind='blank'))
        else:
            d.blocks.append(TextBlock(spans=[TextSpan(text=text)], indent=indent))
    return d


def test_display_text_preserves_indent_and_blanks():
    d = _doc([(0, 'Title'), (0, ''), (4, 'Indented body')])
    assert d.display_text() == 'Title\n\n    Indented body'


def test_blank_blocks_are_detected():
    assert TextBlock(kind='blank').is_blank()
    assert TextBlock(spans=[TextSpan(text='   ')]).is_blank()
    assert not TextBlock(spans=[TextSpan(text='x')]).is_blank()


def test_build_diff_html_returns_changes_list():
    # Highly similar paragraphs pair up and produce a word-level "modified".
    old = _doc([(0, 'the quick brown fox jumps'), (0, 'second line stays')])
    new = _doc([(0, 'the quick red fox jumps'), (0, 'second line stays')])
    old_html, new_html, sidebar, changes = build_diff_html(old, new)
    assert isinstance(changes, list)
    assert len(changes) == 1
    assert changes[0]['kind'] == 'mod'
    assert changes[0]['id'] == 'c1'
    assert 'color:#c0392b' in old_html   # removed word red foreground
    assert 'color:#1a7a3c' in new_html   # added word green foreground


def test_added_and_deleted_blocks_tracked():
    old = _doc([(0, 'keep'), (0, 'remove me')])
    new = _doc([(0, 'keep'), (0, 'brand new line')])
    _, _, _, changes = build_diff_html(old, new)
    kinds = {c['kind'] for c in changes}
    # A low-similarity replace becomes a delete + add pair.
    assert kinds <= {'del', 'add', 'mod'}
    assert changes  # at least one change detected


def test_indent_round_trips_through_edit_parser():
    from logic.text_parser import text_to_doc
    text = 'Heading\n\n    nested item\n        deeper'
    assert text_to_doc(text).display_text() == text


def test_resegmentation_is_not_a_change():
    """Same words, paragraph split moved -> word-stream diff sees no change."""
    old = _doc([(0, 'alpha beta gamma delta epsilon zeta eta theta')])
    new = _doc([(0, 'alpha beta gamma delta'), (0, 'epsilon zeta eta theta')])
    _, _, _, changes = build_diff_html(old, new)
    assert changes == []


def test_modification_is_paired_del_add_and_highlighted():
    old = _doc([(0, 'the contribution rate is 4 percent annually')])
    new = _doc([(0, 'the contribution rate is 3 percent annually')])
    old_html, new_html, sidebar, changes = build_diff_html(old, new)
    assert len(changes) == 1
    assert changes[0] == {'id': 'c1', 'kind': 'mod', 'old': '4', 'new': '3'}
    assert '#c0392b' in old_html      # deleted word red foreground in old panel
    assert '#1a7a3c' in new_html      # added word green foreground in new panel
    assert 'bmod' in sidebar          # orange "Modified" badge in change list


def test_pure_addition_is_green_only():
    old = _doc([(0, 'line one'), (0, 'line two')])
    new = _doc([(0, 'line one'), (0, 'inserted line'), (0, 'line two')])
    old_html, new_html, _, changes = build_diff_html(old, new)
    assert [c['kind'] for c in changes] == ['add']
    assert '#1a7a3c' in new_html
    assert '#c0392b' not in old_html


def test_pure_deletion_is_red_only():
    old = _doc([(0, 'keep this'), (0, 'remove this entirely'), (0, 'keep that')])
    new = _doc([(0, 'keep this'), (0, 'keep that')])
    old_html, new_html, _, changes = build_diff_html(old, new)
    assert [c['kind'] for c in changes] == ['del']
    assert '#c0392b' in old_html
    assert '#1a7a3c' not in new_html
