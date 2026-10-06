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
