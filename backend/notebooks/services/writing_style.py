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
_SOURCE = r'(?:the |this )?(?:text|excerpt|passage|document|source|material|article|reading)'
_ABOUT_SOURCE = re.compile(
    r'(?:(?<=^)|(?<=[.!?]\s))\s*(?:'
    # Reporting verbs take a clause, so the rest still reads as a sentence;
    # "lists", "mentions", "describes", "shows" take an object and only go
    # when "that" follows.
    rf'{_SOURCE} (?:states|explains|says|notes|indicates|suggests|argues|claims)(?: that)?\s+'
    rf'|{_SOURCE} (?:mentions|describes|shows|lists) that\s+'
    rf'|according to {_SOURCE},?\s+'
    rf'|as {_SOURCE} (?:explains|states|says|notes|describes),?\s+'
    r'|theo (?:đoạn trích|đoạn văn|văn bản|tài liệu|bài),?\s+'
    r'|(?:đoạn trích|đoạn văn|văn bản|tài liệu) (?:cho biết|nói|nêu|giải thích|chỉ ra)(?: rằng)?\s+'
    r')', re.I)
# The same inside a question: "...based on the excerpt?", "mentioned in the text as".
_QUESTION_SOURCE = re.compile(
    rf',?\s+(?:based on|according to|in|from) {_SOURCE}(?=\s*[?.,]|$)'
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


def tidy_prose(text: str | None) -> str:
    """`text` without dash-as-connector or a chatbot wrapper. Code spans and
    URLs are left as written. A text that is nothing but a wrapper is kept:
    blanking it would hide that the model sent nothing useful."""
    text = (text or '').strip()
    if not text:
        return ''
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
    stripped = _capitalise_sentences(_ABOUT_SOURCE.sub('', stripped)).strip()
    return stripped if stripped else body.strip()


class CleanGeneratedText:
    """Serializer mixin: generated text written before these rules is shown
    tidy, without rewriting what is stored. Name the fields per serializer."""
    question_fields: tuple[str, ...] = ()
    prose_fields: tuple[str, ...] = ()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field in self.question_fields:
            if data.get(field):
                data[field] = tidy_question(data[field])
        for field in self.prose_fields:
            if data.get(field):
                data[field] = tidy_prose(data[field])
        return data
