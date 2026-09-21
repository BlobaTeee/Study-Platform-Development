"""A notebook's cards or questions as CSV.

UTF-8 with a BOM so Excel on Windows shows Vietnamese correctly (without it
Excel guesses the local code page); Anki, Quizlet and Google Sheets are
happy either way. Flashcards are two columns plus provenance, which is the
shape Anki's importer maps to Front/Back with no fiddling.
"""
import csv
import io

FLASHCARD_HEADER = ['front', 'back', 'source']
QUESTION_HEADER = ['question', 'option_a', 'option_b', 'option_c', 'option_d',
                   'correct_answer', 'explanation', 'source']


def flashcards_csv(cards) -> bytes:
    """`cards` carry question, answer and a `source_titles` attribute (list)."""
    return _csv(FLASHCARD_HEADER, (
        [c.question, c.answer, ' / '.join(c.source_titles)] for c in cards))


def questions_csv(questions) -> bytes:
    """`questions` carry question_text, options, correct_answer, explanation,
    and a `source_title` attribute. Extra options beyond four are dropped;
    fewer are padded, so every row has the same shape."""
    def row(q):
        opts = list(q.options or [])[:4]
        opts += [''] * (4 - len(opts))
        return [q.question_text, *opts, q.correct_answer, q.explanation or '', q.source_title]
    return _csv(QUESTION_HEADER, (row(q) for q in questions))


def _csv(header, rows) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerow(header)
    writer.writerows(rows)
    return b'\xef\xbb\xbf' + buf.getvalue().encode('utf-8')
