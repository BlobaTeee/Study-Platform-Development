"""A quote is found even where the PDF's text layer split a syllable
(2026-11-26): a 25-page physics summary kept 3 of its main ideas."""
from notebooks.services.key_points import _find, _grounded, _searchable

TEXT = ('Nội năng của một vật phụ thuộc vào nhiệt độ và thể tích của vật. Quá trình thực hiện công làm cho n ội '
        'năng của vật thay đổi, vật nhận công thì nội năng tăng. Khi hai vật có nhiệt độ khác nhau tiếp xúc với '
        'nhau thì x ảy ra quá trình truy ền nhiệt.')


def test_a_split_syllable_does_not_hide_the_quote():
    flat, _ = _searchable(TEXT)
    assert _find('Quá trình thực hiện công làm cho nội năng của vật thay đổi', flat) is not None
    assert _find('thì xảy ra quá trình truyền nhiệt', flat) is not None


def test_a_quote_the_document_does_not_hold_is_still_dropped():
    flat, _ = _searchable(TEXT)
    assert _find('Động năng trung bình của phân tử tỉ lệ thuận với nhiệt độ tuyệt đối', flat) is None
    assert _find('nội năng', flat) is None                     # too short to count


def test_the_idea_keeps_the_passage_it_came_from():
    [point] = _grounded([{'point': 'Truyền nhiệt xảy ra khi hai vật khác nhiệt độ tiếp xúc.', 'label': 'Truyền nhiệt',
                          'importance': 'core', 'quote': 'thì xảy ra quá trình truyền nhiệt'}], TEXT)
    assert 'x ảy ra' in point['passage']
