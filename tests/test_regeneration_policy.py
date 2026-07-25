"""Which flagged cards get regenerated on a given due-fetch."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "flashcards" / "services" / "regeneration.py")


def _load():
    spec = importlib.util.spec_from_file_location("regeneration_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


select_for_regeneration = _load().select_for_regeneration


def _card(card_id, *, flagged, status="due"):
    return {"id": card_id, "needs_regeneration": flagged, "status": status}


def test_only_flagged_due_cards_are_selected():
    cards = [
        _card(1, flagged=True),
        _card(2, flagged=False),
        _card(3, flagged=True, status="new"),
    ]
    assert [c["id"] for c in select_for_regeneration(cards, limit=5)] == [1]


def test_selection_is_capped_so_one_fetch_cannot_stall():
    cards = [_card(i, flagged=True) for i in range(1, 11)]
    assert len(select_for_regeneration(cards, limit=3)) == 3


def test_nothing_flagged_means_no_work():
    assert select_for_regeneration([_card(1, flagged=False)], limit=5) == []
