"""How the app's generated prose should read: like a teacher, not a chatbot.

`WRITING_STYLE` goes into every prompt that asks for prose: overviews,
explanations, tutor answers, feedback. It condenses Wikipedia's "Signs of AI
writing" (WikiProject AI Cleanup) to the patterns that show up in study
material; the full list is far too long to send with every request.

`tidy_prose` then removes, after the fact, the two tells a prompt does not
reliably stop: dashes used as all-purpose punctuation, and a chatbot's
greeting or sign-off wrapped around the content.
"""
import re

from .units import unit_symbols, unit_symbols_in_math

WRITING_STYLE = """Write plainly, like a good teacher explaining to one student:
- Write about the subject itself. Never mention "the excerpt", "the text", "the passage", "the
  document", "the author says" or "đoạn trích": the student never sees an excerpt.
- Give the concrete reason or fact. Avoid empty verbs: ensure, aim to, help to, allow, enable, foster,
  create a sense of. Do not stack adjectives ("ordinary, inclusive, and accessible").
- State each point directly. No "not X but Y", "rather than" or "không chỉ... mà còn" contrasts that only
  add weight, no one-line closer that repeats the point, no "let's dive in" lead-in.
- No em dashes or en dashes. Use a comma, colon, period or parentheses.
- Use plain verbs (is, are, has), not "serves as", "stands as" or "đóng vai trò".
- Avoid stock words: crucial, pivotal, key (adjective), delve, underscore, highlight (verb), showcase,
  robust, vibrant, landscape, seamless, testament, enhance, additionally, "quan trọng" for emphasis.
- No greeting, praise or sign-off. No markdown, bold or emojis. Say nothing the material does not support.
- Write a unit after a number as its symbol: 500 J, 2 Pa, 10 N, 3 m/s, 220 V, 5 kg, 25 °C, 2 h. Never spell
  it out ("500 joule", "2 pascal", "10 niutơn", "3 mét trên giây").
Instead of: "Adopting standard conventions ensures that the experience feels ordinary, inclusive, and
accessible, as the text explains."
Write: "Most apps use a bottom bar and a map, so an app that looks the same doesn't mark its users
as different."
Instead of: "Photosynthesis plays a key role in enabling plants to create energy."
Write: "Plants turn light, water and carbon dioxide into glucose, which they burn for energy." """

# A dash between two digits is a range ("3–5 sentences"): it becomes a hyphen.
_RANGE = re.compile(r'(?<=\d)\s*[–—]\s*(?=\d)')
# Any other em or en dash, or a spaced double hyphen, is a clause break.
_DASH = re.compile(r'\s*[—–]\s*|\s+--\s+')
_CODE_OR_URL = re.compile(r'`[^`]*`|https?://\S+')
# Maths in LaTeX ($$...$$ display, $...$ inline) is held out of every rule.
_MATH = re.compile(r'\$\$.+?\$\$|\$[^$\n]+?\$', re.S)

_OPENERS = re.compile(
    r'^\s*(?:great question|good question|certainly|of course|sure|absolutely|'
    r'câu hỏi hay|câu hỏi rất hay|chắc chắn rồi|tất nhiên)\s*[!.,:]+\s*', re.I)
_CLOSERS = re.compile(
    r'\s*(?:i hope (?:this|that) helps|hope (?:this|that) helps|'
    r'let me know if[^.!?]*|feel free to ask[^.!?]*|'
    r'hy vọng (?:điều|thông tin|lời giải thích) (?:này|trên) (?:sẽ )?giúp ích(?: (?:được )?cho bạn)?|'
    r'chúc bạn học tốt)\s*[.!]*\s*$', re.I)


# The model writing about its own input instead of the subject. Removed at the
# start of a sentence; the sentence keeps its claim.
_SOURCE = (r'(?:the |this )?(?:(?:first|second|third|last|opening|final|next) '
           r'(?:sentence|line|paragraph|part|section) of (?:the |this )?)?'
           r'(?:(?:provided|given|above|following|tutorial|lecture|attached|source) )?'
           r'(?:text|excerpt|passage|document|source|material|article|reading)')
_ADVERB = r'(?:\w+ly )?'
# Verbs that take a clause: dropping "The excerpt explicitly states" leaves
# a sentence. Verbs that take an object only go when "that" follows.
_CLAUSE_VERBS = (r'(?:states|explains|says|notes|indicates|suggests|argues|claims|specifies|clarifies|'
                 r'confirms|emphasi[sz]es|highlights|stresses|points out|reports|concludes)')
_OBJECT_VERBS = (r'(?:mentions|describes|shows|lists|identifies|outlines|names|defines|presents|'
                 r'gives|includes|discusses|covers|refers to|links|cites|connects|compares|contrasts|'
                 r'introduces|provides|offers|uses|frames|ties|associates|attributes|recommends)')
_SENTENCE_START = r'(?:(?<=^)|(?<=[.!?]\s))\s*'
_ABOUT_SOURCE = re.compile(
    _SENTENCE_START + r'(?:'
    rf'{_SOURCE} {_ADVERB}{_CLAUSE_VERBS}(?: that)?,?\s+'
    rf'|{_SOURCE} {_ADVERB}{_OBJECT_VERBS} that\s+'
    rf'|according to {_SOURCE},?\s+'
    rf'|as {_SOURCE} {_ADVERB}(?:explains|states|says|notes|describes),?\s+'
    r'|theo (?:đoạn trích|đoạn văn|văn bản|tài liệu|bài),?\s+'
    r'|(?:đoạn trích|đoạn văn|văn bản|tài liệu) (?:cho biết|nói|nêu|giải thích|chỉ ra)(?: rằng)?\s+'
    r')', re.I)
# "The excerpt states, 'Mobile phones are a lifeline.'": the quote is the claim.
_QUOTED = re.compile(
    _SENTENCE_START + rf'{_SOURCE} {_ADVERB}(?:states|says|notes|explains|writes|reads)[,:]\s*'
    # The closing quote is the one the sentence ends on; an apostrophe inside
    # the quote ("a device's value") is not it.
    r'[\'"“‘](?P<quote>.+?)[.!?]?[\'"”’]\s*[.!?]?(?=\s*$|\s+[A-Z])', re.I)
# "The excerpt lists X as Y" keeps its verb; the document's name takes the
# subject's place, since without a subject the sentence would be a fragment.
# "...are not mentioned in the text": inside a sentence, the name replaces it.
_IN_SOURCE = re.compile(r'\b(in|from|by) (?:the |this )(?:excerpt|text|passage)\b', re.I)
# Any verb, not a list of them ("prioritizes", "frames"): the list never ends.
_OBJECT_SUBJECT = re.compile(_SENTENCE_START + rf'{_SOURCE} {_ADVERB}(?=[a-z]+s\b)', re.I)
# The same inside a question: "...based on the excerpt?", "mentioned in the text as".
_QUESTION_SOURCE = re.compile(
    rf',?\s+(?:based on|according to|in|from) {_SOURCE}(?=\s*[?.,]|$)'
    # "a key finding of the article regarding X": the noun stands without it.
    rf'|\s+of {_SOURCE}(?=\s+(?:regarding|about|on|concerning)\b)'
    rf'|\b(?:mentioned|described|listed|stated|named) in {_SOURCE}(?: as)?\s+'
    r'|\s+(?:trong|theo) (?:đoạn trích|đoạn văn|văn bản|tài liệu)(?=\s*[?.,]|$)', re.I)


def _capitalise_sentences(text: str) -> str:
    return re.sub(r'(^|[.!?]\s+)([a-zà-ỹ])', lambda m: m.group(1) + m.group(2).upper(), text)


def tidy_question(text: str | None) -> str:
    """A question without "based on the excerpt" and its relatives."""
    text = (text or '').strip()
    if not text:
        return ''
    body = _QUESTION_SOURCE.sub(lambda m: ' ' if m.group(0).endswith(' ') and not m.group(0).startswith((',', ' ')) else '', text)
    body = _ABOUT_SOURCE.sub('', body)
    body = re.sub(r'\s+([?.,])', r'\1', re.sub(r'\s{2,}', ' ', body)).strip()
    return tidy_prose(_capitalise_sentences(body)) or text


def tidy_prose(text: str | None, source_title: str = '') -> str:
    """`text` without dash-as-connector, a chatbot wrapper, or talk about
    "the excerpt". Code spans and URLs are left as written. A text that is
    nothing but a wrapper is kept: blanking it would hide that the model sent
    nothing useful. `source_title` names the document a sentence like "The
    text lists X" is about, so it can say "CityHelp lists X" instead."""
    text = (text or '').strip()
    if not text:
        return ''
    maths: list[str] = []

    def hold_math(m):
        maths.append(m.group(0))
        return f'\x01{len(maths) - 1}\x01'

    def put_math_back(t: str) -> str:
        return re.sub(r'\x01(\d+)\x01', lambda m: maths[int(m.group(1))], t)

    text = unit_symbols(_MATH.sub(hold_math, text))
    maths[:] = [unit_symbols_in_math(m) for m in maths]
    kept: list[str] = []

    def hold(m):
        kept.append(m.group(0))
        return f'\x00{len(kept) - 1}\x00'

    body = _CODE_OR_URL.sub(hold, text)
    body = _RANGE.sub('-', body)
    body = _DASH.sub(', ', body)
    body = re.sub(r',\s*([,.;:!?])', r'\1', body)       # "word, ." left by a trailing dash
    body = re.sub(r'\x00(\d+)\x00', lambda m: kept[int(m.group(1))], body)

    stripped = _CLOSERS.sub('', _OPENERS.sub('', body, count=1), count=1).strip()
    stripped = _QUOTED.sub(lambda m: m.group('quote').strip() + '. ', stripped).strip()
    stripped = _ABOUT_SOURCE.sub('', stripped)
    if source_title:
        stripped = _IN_SOURCE.sub(lambda m: f'{m.group(1)} {source_title.strip()}', stripped)
        stripped = _OBJECT_SUBJECT.sub(lambda m: m.group(0)[:len(m.group(0)) - len(m.group(0).lstrip())]
                                       + source_title.strip() + ' ', stripped)
    stripped = _capitalise_sentences(stripped).strip()
    return put_math_back(stripped if stripped else body.strip())


class CleanGeneratedText:
    """Serializer mixin: generated text written before these rules is shown
    tidy, without rewriting what is stored. Name the fields per serializer."""
    question_fields: tuple[str, ...] = ()
    prose_fields: tuple[str, ...] = ()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        title = _title_of(instance) if self.prose_fields else ''
        for field in self.question_fields:
            if data.get(field):
                data[field] = tidy_question(data[field])
        for field in self.prose_fields:
            if data.get(field):
                data[field] = tidy_prose(data[field], source_title=title)
        return data


#: Stands in for a document whose name is not known (an older question, or
#: one whose document was deleted): what a teacher would say.
UNNAMED_SOURCE = 'The reading'


def _title_of(instance) -> str:
    """The document a question or card came from, by name, or "The reading"."""
    # A mock-test row keeps its own copy of the source, and a link back to
    # the question it was drawn from, which may know more.
    question = getattr(instance, 'question', None)
    for item in (instance, question):
        source = getattr(item, 'source', None)
        if source is not None:
            return source.title
    for holder in (instance, getattr(instance, 'quiz', None), getattr(question, 'quiz', None)):
        sources = getattr(holder, 'sources', None)
        if sources is not None:
            named = [s.title for s in sources.all()[:2]]
            if len(named) == 1:
                return named[0]
    return UNNAMED_SOURCE
