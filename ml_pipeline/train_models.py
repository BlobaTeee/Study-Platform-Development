"""Bake-off training + evaluation for the SciQ answer scorer."""
from __future__ import annotations

import datetime as dt
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, confusion_matrix,
                             f1_score, roc_auc_score)
from sklearn.svm import LinearSVC

from . import config
from .answer_scorer import AnswerScorer
from .features.answer_features import FeatureBuilder, expand_candidates, token_overlap


def _candidates():
    return {
        "logreg": LogisticRegression(class_weight="balanced", max_iter=1000,
                                     random_state=config.RANDOM_SEED),
        "linsvc": LinearSVC(class_weight="balanced",
                            random_state=config.RANDOM_SEED),
        "rf": RandomForestClassifier(n_estimators=200, max_depth=None,
                                     class_weight="balanced", n_jobs=-1,
                                     random_state=config.RANDOM_SEED),
    }


def accuracy_at_1(scorer: AnswerScorer, long_df: pd.DataFrame) -> float:
    """Per question: is the highest-scored candidate the correct one?"""
    probs = scorer.predict_proba(long_df)
    tmp = long_df.assign(_p=probs)
    hits = []
    for _, grp in tmp.groupby("question_id"):
        top = grp.loc[grp["_p"].idxmax()]
        hits.append(int(top["is_correct"] == 1))
    return float(np.mean(hits))


def compute_baselines(train_long: pd.DataFrame, eval_long: pd.DataFrame) -> dict:
    """Reference floors: random chance, the support-overlap heuristic, and a
    stratified Dummy classifier — so the trained model's lift is quantified."""
    # Support-overlap-only ranker: pick the candidate most present in support.
    ov = [token_overlap(c, s)
          for c, s in zip(eval_long["candidate"], eval_long["support"])]
    tmp = eval_long.assign(_ov=ov)
    hits = [int(g.loc[g["_ov"].idxmax()]["is_correct"] == 1)
            for _, g in tmp.groupby("question_id")]
    support_overlap_at_1 = float(np.mean(hits))

    # Random selection among the candidates of each question.
    random_at_1 = float(1.0 / eval_long.groupby("question_id").size().mean())

    # Stratified Dummy classifier for candidate-level context.
    dummy = DummyClassifier(strategy="stratified", random_state=config.RANDOM_SEED)
    dummy.fit(np.zeros((len(train_long), 1)), train_long["is_correct"].to_numpy())
    y = eval_long["is_correct"].to_numpy()
    dprob = dummy.predict_proba(np.zeros((len(eval_long), 1)))[:, 1]
    dpred = (dprob >= 0.5).astype(int)
    return {
        "random_at_1": round(random_at_1, 4),
        "support_overlap_at_1": support_overlap_at_1,
        "dummy_f1": float(f1_score(y, dpred, zero_division=0)),
        "dummy_roc_auc": (float(roc_auc_score(y, dprob))
                          if len(set(y)) > 1 else float("nan")),
    }


def evaluate(scorer: AnswerScorer, test_long: pd.DataFrame) -> dict:
    probs = scorer.predict_proba(test_long)
    preds = (probs >= 0.5).astype(int)
    y = test_long["is_correct"].to_numpy()
    return {
        "f1": float(f1_score(y, preds)),
        "roc_auc": float(roc_auc_score(y, probs)) if len(set(y)) > 1 else float("nan"),
        "pr_auc": float(average_precision_score(y, probs)) if len(set(y)) > 1 else float("nan"),
        "accuracy_at_1": accuracy_at_1(scorer, test_long),
    }


def _save_reports(best_name, best_scorer, val_comparison, test_metrics, baselines, test_long):
    config.ensure_dirs()
    (config.REPORTS_DIR / "metrics.json").write_text(json.dumps({
        "best_model": best_name,
        "selection_metric": "accuracy_at_1",
        "selection_split": "validation",
        "validation_comparison": val_comparison,
        "test_metrics": test_metrics,
        "baselines": baselines,
    }, indent=2))
    pd.DataFrame(val_comparison).T.to_csv(config.REPORTS_DIR / "model_comparison.csv")

    probs = best_scorer.predict_proba(test_long)
    preds = (probs >= 0.5).astype(int)
    cm = confusion_matrix(test_long["is_correct"], preds)
    fig, ax = plt.subplots()
    ax.imshow(cm, cmap="Blues")
    for (i, j), v in np.ndenumerate(cm):
        ax.text(j, i, str(v), ha="center", va="center")
    ax.set(xlabel="predicted", ylabel="true", title=f"Confusion — {best_name}")
    fig.savefig(config.REPORTS_DIR / "confusion.png", bbox_inches="tight")
    plt.close(fig)

    clf = best_scorer.classifier
    importances = getattr(clf, "feature_importances_", None)
    if importances is None:
        importances = np.abs(np.ravel(getattr(clf, "coef_", np.zeros(len(FeatureBuilder.FEATURE_NAMES)))))
    fig, ax = plt.subplots()
    ax.barh(FeatureBuilder.FEATURE_NAMES, importances)
    ax.set_title(f"Feature importance — {best_name}")
    fig.savefig(config.REPORTS_DIR / "feature_importance.png", bbox_inches="tight")
    plt.close(fig)

    (config.REPORTS_DIR / "model_card.json").write_text(json.dumps({
        "model": best_name,
        "trained_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
        "test_metrics": test_metrics,
        "baselines": baselines,
        "features": FeatureBuilder.FEATURE_NAMES,
    }, indent=2))


def train_all(sciq_df: pd.DataFrame | None = None, save: bool = True) -> dict:
    if sciq_df is None:
        from .dataset_loader import load_processed
        sciq_df = load_processed("sciq")

    long = expand_candidates(sciq_df)
    train_long = long[long["split"] == "train"]
    val_long = long[long["split"] == "val"]
    test_long = long[long["split"] == "test"]
    # tiny-data guard: fall back to the test split if no validation rows exist
    if len(val_long) == 0:
        val_long = test_long
    final_split = test_long if len(test_long) else val_long

    # 1. Compare every model on the SAME validation split.
    val_comparison, scorers = {}, {}
    for name, clf in _candidates().items():
        scorer = AnswerScorer(classifier=clf).fit(train_long)
        scorers[name] = scorer
        val_comparison[name] = evaluate(scorer, val_long)

    # 2. Select the winner by the headline product metric.
    best_name = max(val_comparison, key=lambda n: val_comparison[n]["accuracy_at_1"])
    best_scorer = scorers[best_name]

    # 3. Score the winner ONCE on the held-out test split, next to the baselines.
    test_metrics = evaluate(best_scorer, final_split)
    baselines = compute_baselines(train_long, final_split)

    if save:
        best_scorer.save(config.MODELS_DIR / "answer_scorer.joblib")
        _save_reports(best_name, best_scorer, val_comparison, test_metrics,
                      baselines, final_split)

    return {
        "best_model": best_name,
        "selection_metric": "accuracy_at_1",
        "validation_comparison": val_comparison,
        "test_metrics": test_metrics,
        "baselines": baselines,
    }


def main() -> None:
    result = train_all()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
