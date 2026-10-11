"""A document's main ideas, read once from the whole text.

Generation used to pick three passages by word statistics from the first
18,000 characters: most of a long document was never asked about, and the
picks followed keyword density rather than what the document is about. Now
the model reads the whole document (up to `MAX_READ_CHARS`) and lists its
main ideas, core ones first, each with a sentence quoted from the text.

The quote is how an idea stays grounded. It is looked up in the document,
allowing for the small changes models make when copying (case, spacing,
curly quotes); an idea whose quote cannot be found is dropped, since the
document may not say it. The passage around the quote travels with the idea,
so a question written from it can still point the student at what to reread.
"""
import logging
import re

from ml_pipeline.language import detect_language, language_name

from .ai_provider import get_ai_provider
from .textnorm import clean_summary
from .writing_style import WRITING_STYLE, tidy_prose

logger = logging.getLogger(__name__)

#: About 30,000 tokens: a long lecture or paper in one request.
MAX_READ_CHARS = 120_000
MAX_POINTS = 15
IMPORTANCE = ('core', 'supporting')
#: Characters of text kept around a quote as the idea's passage.
PASSAGE_CHARS = 1500


def read_document(text: str, title: str, subject_language: str | None = None) -> dict:
    """One request: {summary, key_points, subject}. `subject` is asked for
    only when `subject_language` is given (an upload placing itself). Any
    failure returns empty values; reading never blocks an upload."""
    text = text or ''
    read = text[:MAX_READ_CHARS]
    doc_language = language_name(detect_language(text))
    subject_ask = (f'\n- "subject": the school subject or course it belongs to, as a notebook title of 2 to 5 '
                   f'words in {language_name(subject_language)}, general enough that other lectures of the same '
                   f'course fit under it.' if subject_language else '')
    prompt = f"""A student uploaded a document titled "{title}". Read all of it, then return:
- "summary": an overview of 3 to 5 sentences, in {doc_language}.
- "key_points": its main ideas, at most {MAX_POINTS}, the most important first. For each:
  "point": the idea in one or two sentences, in {doc_language};
  "label": the same idea as a short heading of 2 to 6 words, in {doc_language};
  "importance": "core" for what a student must know to pass, "supporting" for the rest;
  "quote": one sentence copied word for word from the document that states or supports it.
  Cover the whole document, its end as much as its start. Skip incidental details (page
  counts, sample sizes, dates of publication) unless they are the point.{subject_ask}

{WRITING_STYLE}

Document text:
{read}

Return ONLY valid JSON: {{"summary": "...", "key_points": [{{"point": "...", "label": "...", "importance": "core|supporting", "quote": "..."}}]{', "subject": "..."' if subject_language else ''}}}"""
    try:
        data = get_ai_provider().generate_json(prompt)
    except Exception as exc:  # noqa: BLE001 — no provider, quota, bad JSON
        logger.info('Reading the document failed: %s', exc)
        return {'summary': '', 'key_points': [], 'subject': ''}
    data = data if isinstance(data, dict) else {}
    return {
        'summary': clean_summary(str(data.get('summary') or '').strip()),
        'key_points': _grounded(data.get('key_points'), text),
        'subject': str(data.get('subject') or '').strip().strip('."\'')[:60],
    }


def ensure_key_points(source) -> list[dict]:
    """The source's main ideas, read now if it has none yet (one request,
    kept). Fills an empty overview from the same request."""
    if source.key_points:
        return source.key_points
    if not (source.extracted_text or '').strip():
        return []
    out = read_document(source.extracted_text, source.title)
    if not out['key_points']:
        return []
    source.key_points = out['key_points']
    fields = ['key_points']
    if not source.gemini_summary and out['summary']:
        source.gemini_summary = out['summary']
        fields.append('gemini_summary')
    source.save(update_fields=fields)
    return source.key_points


def _grounded(raw, text: str) -> list[dict]:
    if not isinstance(raw, list):
        return []
    flat, index = _searchable(text)
    points = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        point = tidy_prose(str(item.get('point') or ''))
        quote = str(item.get('quote') or '')
        at = _find(quote, flat)
        if not point or at is None:
            continue
        start = index[at]
        points.append({
            'point': point[:400],
            'label': _label(item.get('label')),
            'importance': item.get('importance') if item.get('importance') in IMPORTANCE else 'supporting',
            'passage': _passage_around(text, start),
        })
    # Core first, keeping the model's order within each.
    points.sort(key=lambda p: IMPORTANCE.index(p['importance']))
    return points[:MAX_POINTS]


#: A label is a heading: past this many words it is a sentence again.
MAX_LABEL_WORDS = 8


def _label(raw) -> str:
    label = tidy_prose(str(raw or '')).strip().rstrip('.')
    return label if 0 < len(label.split()) <= MAX_LABEL_WORDS else ''


_SPACE = re.compile(r'\s+')
_QUOTE_MARKS = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"'})


def _normalise(s: str) -> str:
    return s.translate(_QUOTE_MARKS).lower()


def _searchable(text: str) -> tuple[str, list[int]]:
    """The text lowercased with runs of space collapsed, and for each of its
    characters the position it came from in the original."""
    flat, index, prev_space = [], [], False
    for i, ch in enumerate(_normalise(text)):
        if ch.isspace():
            if prev_space:
                continue
            ch, prev_space = ' ', True
        else:
            prev_space = False
        flat.append(ch)
        index.append(i)
    return ''.join(flat), index


def _find(quote: str, flat: str) -> int | None:
    needle = _SPACE.sub(' ', _normalise(quote)).strip().strip('."\'')
    if len(needle) < 20:
        return None      # too short to stand as evidence
    at = flat.find(needle)
    if at < 0 and len(needle) > 60:
        # A long quote with a small slip further on: its opening still has to
        # be in the document word for word.
        at = flat.find(needle[:60])
    return at if at >= 0 else None


def _passage_around(text: str, start: int) -> str:
    """The paragraph-sized stretch of text the quote sits in."""
    left = max(0, start - PASSAGE_CHARS // 3)
    right = min(len(text), start + PASSAGE_CHARS)
    # Start and end on sentence boundaries where there is one nearby.
    head = text.rfind('. ', left, start)
    left = head + 2 if head != -1 else left
    tail = text.find('. ', start + 200, right)
    right = tail + 1 if tail != -1 else right
    return text[left:right].strip()
