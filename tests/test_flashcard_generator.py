from ml_pipeline.services.flashcard_generator import FlashcardGenerator


def _gen(candidates, fake_extractor_factory):
    return FlashcardGenerator(extractor=fake_extractor_factory(candidates))


def test_definitional_card_for_nominal_entity(sample_candidates, fake_extractor_factory):
    gen = _gen(sample_candidates, fake_extractor_factory)
    cards = gen.generate("ignored", count=10)
    einstein = [c for c in cards if c["answer"].startswith("Albert Einstein")]
    assert einstein
    assert einstein[0]["question"] == "What is Albert Einstein?"
    assert set(einstein[0]) == {"question", "answer", "difficulty"}
    assert einstein[0]["difficulty"] in {"easy", "medium", "hard"}


def test_cloze_card_for_noun_chunk(sample_candidates, fake_extractor_factory):
    gen = _gen(sample_candidates, fake_extractor_factory)
    cards = gen.generate("ignored", count=10)
    powerhouse = [c for c in cards if c["answer"] == "powerhouse"]
    assert powerhouse
    assert "______" in powerhouse[0]["question"]
    assert "powerhouse" not in powerhouse[0]["question"]


def test_count_is_respected(sample_candidates, fake_extractor_factory):
    gen = _gen(sample_candidates, fake_extractor_factory)
    assert len(gen.generate("ignored", count=2)) == 2


def test_zero_or_empty_returns_empty(sample_candidates, fake_extractor_factory):
    gen = _gen(sample_candidates, fake_extractor_factory)
    assert gen.generate("ignored", count=0) == []
    assert FlashcardGenerator(extractor=fake_extractor_factory([])).generate("x", count=5) == []
