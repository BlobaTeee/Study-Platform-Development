"""Django management command to retrain ML models from platform data."""

from django.core.management.base import BaseCommand

from flashcards.models import Flashcard


class Command(BaseCommand):
    help = "Retrain ML models using platform flashcard/quiz performance data"

    def handle(self, *args, **options):
        import pandas as pd
        from ml_pipeline.config import PROCESSED_DIR
        from ml_pipeline.retrain_from_platform import retrain_all

        sciq_path = PROCESSED_DIR / "sciq.parquet"
        hierarchy_path = PROCESSED_DIR / "topic_hierarchy.parquet"
        flashcards_path = PROCESSED_DIR / "flashcards.parquet"

        if not sciq_path.exists() or not hierarchy_path.exists():
            self.stderr.write(
                "Processed datasets missing. Run ml_pipeline/notebooks/01_eda.ipynb first."
            )
            return

        sciq_df = pd.read_parquet(sciq_path)
        hierarchy_df = pd.read_parquet(hierarchy_path)
        flashcards_df = pd.read_parquet(flashcards_path) if flashcards_path.exists() else None

        reviewed = Flashcard.objects.filter(correct_count__gt=0) | Flashcard.objects.filter(
            incorrect_count__gt=0
        )
        platform_cards = reviewed if reviewed.exists() else Flashcard.objects.all()

        self.stdout.write(f"Platform flashcards for retraining: {platform_cards.count()}")
        results = retrain_all(platform_cards, sciq_df, hierarchy_df, flashcards_df)

        for name, info in results.items():
            self.stdout.write(f"  {name}: {info}")

        self.stdout.write(self.style.SUCCESS("Retraining complete."))
