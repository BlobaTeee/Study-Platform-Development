"""Bayesian Knowledge Tracing: the chance a skill is known, after each answer."""
import random

from ml_pipeline.bkt import Params, fit, kind_of, load, neg_log_likelihood, p_correct, trace, update

P = Params(init=0.3, learn=0.2, slip=0.1, guess_choice=0.25, guess_written=0.1)


def test_a_right_answer_raises_the_chance_and_a_wrong_one_lowers_it():
    assert update(0.5, True, 'choice', P) > 0.5
    assert update(0.5, False, 'choice', P) < 0.5 + P.learn


def test_a_right_multiple_choice_answer_counts_for_less_than_a_written_one():
    # Guessing a 1-in-4 option is easier than guessing a written answer.
    assert update(0.3, True, 'choice', P) < update(0.3, True, 'written', P)


def test_p_correct_mixes_knowing_and_guessing():
    assert p_correct(1.0, 'written', P) == 1 - P.slip
    assert p_correct(0.0, 'choice', P) == P.guess_choice


def test_trace_of_nothing_is_the_prior_and_a_run_of_right_answers_approaches_one():
    assert trace([], P) == P.init
    assert trace([(True, 'written')] * 8, P) > 0.95


def test_answer_types_map_to_two_kinds():
    assert kind_of('choose_1') == 'choice' and kind_of('choose_n') == 'choice'
    assert kind_of('algebra') == 'written' and kind_of('fill_in_1') == 'written'


def test_fit_recovers_parameters_from_simulated_students():
    rng = random.Random(3)
    true = Params(init=0.2, learn=0.25, slip=0.08, guess_choice=0.3, guess_written=0.05)
    seqs = []
    for _ in range(400):
        known = rng.random() < true.init
        seq = []
        for _ in range(10):
            kind = 'choice' if rng.random() < 0.5 else 'written'
            guess = true.guess_choice if kind == 'choice' else true.guess_written
            right = (rng.random() > true.slip) if known else (rng.random() < guess)
            seq.append((right, kind))
            known = known or rng.random() < true.learn
        seqs.append(seq)
    got = fit(seqs)
    assert abs(got.learn - true.learn) < 0.08 and abs(got.guess_choice - true.guess_choice) < 0.08
    assert neg_log_likelihood(seqs, got) <= neg_log_likelihood(seqs, P)


def test_shipped_parameters_load_with_thresholds():
    params, thresholds = load()
    assert 0 < params.init < 1 and thresholds['strong'] > thresholds['shaky']
