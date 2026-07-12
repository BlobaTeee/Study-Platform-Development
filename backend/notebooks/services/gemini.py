from django.conf import settings

def summarize_with_gemini(text: str, title: str = '') -> str:
    """
    Generate a short NotebookLM-style overview using Gemini.
    Returns empty string if API key is missing or the call fails.
    """
    if not getattr(settings, 'GEMINI_API_KEY', '') or not text.strip():
        return ''

    snippet = text[:30000]
    prompt = (
        f'You are a study assistant. The document is titled "{title or "Untitled"}".\n'
        'Write a clear 3–5 sentence overview of the main topics and key takeaways.\n'
        'Return plain text only (no JSON, no markdown headings).\n\n'
        f'Document text:\n{snippet}'
    )

    try:
        from .gemini_client import _get_client
        client = _get_client()
        response = client.models.generate_content(
            model=getattr(settings, 'GEMINI_MODEL', 'gemini-2.0-flash'),
            contents=prompt,
        )
        return (response.text or '').strip()
    except Exception:
        return ''
