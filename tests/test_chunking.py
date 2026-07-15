"""Chunking + salience selection for document-grounded generation."""
import pytest

from ml_pipeline.services.chunking import chunk_text, select_chunks


def _sentences(n, word="alpha"):
    return " ".join(f"This is sentence number {i} about {word} topics." for i in range(n))


# ---- chunk_text ------------------------------------------------------------

def test_short_text_is_a_single_chunk():
    text = "One short sentence. Another short one."
    assert chunk_text(text, target_chars=1000) == [text]


def test_empty_text_returns_no_chunks():
    assert chunk_text("", target_chars=100) == []
    assert chunk_text("   \n ", target_chars=100) == []


def test_long_text_splits_into_multiple_chunks_under_target():
    text = _sentences(60)
    chunks = chunk_text(text, target_chars=300, overlap_sentences=0)
    assert len(chunks) > 1
    # No chunk wildly exceeds the target (a lone long sentence may, none here).
    assert all(len(c) <= 300 for c in chunks)


def test_chunks_do_not_cut_mid_sentence():
    text = _sentences(40)
    for c in chunk_text(text, target_chars=300, overlap_sentences=0):
        assert c.endswith(".")


def test_overlap_repeats_boundary_sentence_for_context():
    text = _sentences(30)
    chunks = chunk_text(text, target_chars=300, overlap_sentences=1)
    # The first sentence of chunk 2 should be the last sentence of chunk 1.
    first_tail = chunks[0].split(". ")[-1].strip(". ")
    assert first_tail and first_tail in chunks[1]


def test_single_sentence_longer_than_target_is_kept_not_dropped():
    long_sentence = "word " * 200 + "end."
    chunks = chunk_text(long_sentence, target_chars=100)
    assert len(chunks) == 1
    assert "end." in chunks[0]


def test_no_content_is_lost_across_chunks():
    text = _sentences(25)
    joined = " ".join(chunk_text(text, target_chars=300, overlap_sentences=0))
    for i in range(25):
        assert f"sentence number {i} " in joined


# ---- select_chunks ---------------------------------------------------------

def test_selects_at_most_k():
    chunks = [_sentences(3, f"w{i}") for i in range(10)]
    assert len(select_chunks(chunks, k=3)) == 3


def test_returns_all_when_fewer_than_k():
    chunks = ["Alpha content here.", "Beta content here."]
    assert select_chunks(chunks, k=5) == chunks


def test_k_zero_or_negative_returns_empty():
    assert select_chunks(["a", "b"], k=0) == []
    assert select_chunks(["a", "b"], k=-1) == []


def test_empty_chunks_returns_empty():
    assert select_chunks([], k=3) == []


def test_selected_chunks_keep_document_order():
    chunks = [f"Chunk {i} discusses {w}." for i, w in
              enumerate(["alpha", "beta", "gamma", "delta", "epsilon"])]
    out = select_chunks(chunks, k=3)
    assert out == [c for c in chunks if c in out]  # relative order preserved
