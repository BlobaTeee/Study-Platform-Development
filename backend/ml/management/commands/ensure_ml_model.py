"""Ensure the answer-scorer artifact exists — run as a deploy/build step.

The model (answer_scorer.joblib) is gitignored and regenerable, so a fresh
deploy has no artifact. This trains it from the committed processed datasets
(datasets/processed/sciq.parquet) if it is missing. Idempotent; use --force to
retrain unconditionally (e.g. after a scikit-learn upgrade).
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Train the answer-scorer model if the artifact is missing (deploy step)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Retrain even if the artifact already exists.",
        )

    def handle(self, *args, **options):
        from ml_pipeline import config
        from ml_pipeline.train_models import train_all

        model_path = config.MODELS_DIR / "answer_scorer.joblib"

        if model_path.exists() and not options["force"]:
            self.stdout.write(f"Model already present at {model_path}; nothing to do.")
            return

        action = "Retraining" if model_path.exists() else "Training"
        self.stdout.write(f"{action} answer scorer -> {model_path}")
        result = train_all(save=True, with_beyond_science=True)
        self.stdout.write(
            f"  best_model={result['best_model']} "
            f"accuracy@1={result['test_metrics']['accuracy_at_1']:.4f}"
        )
        self.stdout.write(self.style.SUCCESS("Model artifact is ready."))
