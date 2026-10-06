"""What a flashcard's two sides should hold, shared by every prompt that
writes one.

The answer is what a student has to recall, so it stays a short phrase; a
whole sentence on the back cannot be remembered word for word, and a student
grading themselves on it never knows whether "roughly" counts. The reasoning
goes in the explanation, read once the answer is out.
"""
import re

ANSWER_RULES = """The "answer" is what the student must recall: a short phrase of at most
12 words, holding only the key words. No full sentences, and do not repeat
the question. Put the reasoning or extra detail in "explanation" (one or two
sentences), which the student reads after answering.
If a question would need a list of more than three items, write
separate flashcards instead, each asking for one part."""

BLANK = '___'

CLOZE_RULES = """About one card in three should be fill-in-the-blank, for definitions and
key terms: "kind": "cloze", the "question" is one sentence from the excerpt
with exactly one key term replaced by ___, and the "answer" is that hidden
term (one to four words). Every other card is "kind": "basic"."""

# A key term, not a clause. Counted in words, so Vietnamese (one word per
# syllable) gets a little more room than the prompt's "one to four".
MAX_CLOZE_ANSWER_WORDS = 6

_RUN_OF_UNDERSCORES = re.compile(r'_{3,}')


def checked_cloze(question: str, answer: str) -> str | None:
    """The cloze sentence with its blank written as `BLANK`, or None when the
    card cannot be played: no blank or more than one, a hidden word that is
    a whole clause, or one the sentence still shows elsewhere."""
    question = _RUN_OF_UNDERSCORES.sub(BLANK, question)
    if question.count(BLANK) != 1:
        return None
    if not answer or len(answer.split()) > MAX_CLOZE_ANSWER_WORDS:
        return None
    if re.search(rf'(?<!\w){re.escape(answer)}(?!\w)', question, re.IGNORECASE):
        return None
    return question


def spread_cloze(cards: list[dict]) -> list[dict]:
    """The deck with its cloze cards spread through it, one second from
    each end. Models tend to write them last, and a deck is studied from
    one end — today's queue takes the oldest card first, the deck page
    shows the newest first — so left alone a student met them at the end
    of the deck or not at all. Reading the same both ways serves both."""
    cloze = [c for c in cards if c['kind'] == 'cloze']
    basic = [c for c in cards if c['kind'] != 'cloze']
    n, k = len(cards), len(cloze)
    if not cloze or not basic:
        return cards
    if k == 1 or n < 4:
        slots = {min(1, n - 1) + i for i in range(k)}
    else:
        slots = {1 + round(i * (n - 3) / (k - 1)) for i in range(k)}
    out, cloze_iter, basic_iter = [], iter(cloze), iter(basic)
    for position in range(n):
        pick = next(cloze_iter, None) if position in slots else next(basic_iter, None)
        # A collision in the rounding, or more cloze than basic: whatever is left.
        out.append(pick or next(cloze_iter, None) or next(basic_iter))
    return out
