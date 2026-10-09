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
- State each point directly. No "not X but Y" or "không chỉ... mà còn" contrasts that only add weight,
  no one-line closer that repeats the point, no "let's dive in" or "here's the thing" lead-in.
- No em dashes or en dashes. Use a comma, colon, period or parentheses.
- Give as many items as the material has; do not force lists of three.
- Use plain verbs (is, are, has), not "serves as", "stands as", "boasts" or "đóng vai trò".
- Avoid stock words: crucial, pivotal, key (as an adjective), delve, underscore, highlight (as a verb),
  showcase, robust, vibrant, landscape, tapestry, testament, enhance, foster, additionally, "quan trọng"
  used for emphasis.
- Do not inflate: no "plays a key role", "marks a turning point", "the future looks bright".
- No greeting, praise, offer or sign-off ("Great question", "Certainly", "I hope this helps").
- No markdown, bold, headings or emojis. Vary sentence length.
- Say nothing the material does not support."""

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
    return stripped if stripped else body.strip()
