"""
Dataset manager for loading SQuAD 2.0 and SciQ data for quiz and flashcard generation
"""

import os
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional

class DatasetManager:
    def __init__(self, base_path: str = None):
        if base_path is None:
            base_path = Path(__file__).parent.parent.parent / "datasets" / "processed"
        self.base_path = Path(base_path)
        self._train_data = None
        self._val_data = None
        self._test_data = None
        self._squad_data = None
        self._sciq_data = None

    def load_training_data(self) -> pd.DataFrame:
        """Load training dataset"""
        if self._train_data is None:
            path = self.base_path / "train.parquet"
            if not path.exists():
                raise FileNotFoundError(f"Training data not found at {path}")
            self._train_data = pd.read_parquet(path)
        return self._train_data

    def load_validation_data(self) -> pd.DataFrame:
        """Load validation dataset"""
        if self._val_data is None:
            path = self.base_path / "val.parquet"
            if not path.exists():
                raise FileNotFoundError(f"Validation data not found at {path}")
            self._val_data = pd.read_parquet(path)
        return self._val_data

    def load_test_data(self) -> pd.DataFrame:
        """Load test dataset"""
        if self._test_data is None:
            path = self.base_path / "test.parquet"
            if not path.exists():
                raise FileNotFoundError(f"Test data not found at {path}")
            self._test_data = pd.read_parquet(path)
        return self._test_data

    def load_squad_data(self) -> pd.DataFrame:
        """Load SQuAD-only dataset"""
        if self._squad_data is None:
            path = self.base_path / "squad.parquet"
            if not path.exists():
                path = self.base_path / "squad_processed.parquet"
            if not path.exists():
                raise FileNotFoundError(f"SQuAD data not found at {path}")
            self._squad_data = pd.read_parquet(path)
        return self._squad_data

    def load_sciq_data(self) -> pd.DataFrame:
        """Load SciQ-only dataset"""
        if self._sciq_data is None:
            path = self.base_path / "sciq.parquet"
            if not path.exists():
                path = self.base_path / "sciq_processed.parquet"
            if not path.exists():
                raise FileNotFoundError(f"SciQ data not found at {path}")
            self._sciq_data = pd.read_parquet(path)
        return self._sciq_data

    def get_random_qa_pairs(self, n: int = 10, dataset: str = "all") -> List[Dict]:
        """
        Get random QA pairs from the dataset
        
        Args:
            n: Number of pairs to return
            dataset: 'all', 'squad', or 'sciq'
        
        Returns:
            List of dict with question, answer, context
        """
        if dataset == "all":
            data = self.load_training_data()
        elif dataset == "squad":
            data = self.load_squad_data()
        elif dataset == "sciq":
            data = self.load_sciq_data()
        else:
            raise ValueError(f"Unknown dataset: {dataset}")

        sampled = data.sample(min(n, len(data)))
        return sampled[['question', 'answer', 'context', 'dataset']].to_dict('records')

    def get_qa_pairs_by_keywords(self, keywords: List[str], n: int = 10) -> List[Dict]:
        """
        Get QA pairs containing specific keywords
        
        Args:
            keywords: List of keywords to search for
            n: Maximum number of pairs to return
        
        Returns:
            List of QA pairs matching the keywords
        """
        data = self.load_training_data()
        
        # Filter by context containing keywords
        mask = data['context'].str.contains(
            '|'.join(keywords), case=False, na=False
        )
        
        results = data[mask].sample(min(n, mask.sum()))
        return results[['question', 'answer', 'context', 'dataset']].to_dict('records')

    def get_dataset_stats(self) -> Dict:
        """Get statistics about the datasets"""
        train = self.load_training_data()
        val = self.load_validation_data()
        test = self.load_test_data()
        squad = self.load_squad_data()
        sciq = self.load_sciq_data()

        return {
            'train_size': len(train),
            'val_size': len(val),
            'test_size': len(test),
            'squad_size': len(squad),
            'sciq_size': len(sciq),
            'total_size': len(train) + len(val) + len(test),
            'squad_questions': squad['question_len'].mean() if 'question_len' in squad else None,
            'sciq_questions': sciq['question_len'].mean() if 'question_len' in sciq else None,
        }


# Singleton instance for easy access
_instance = None

def get_dataset_manager() -> DatasetManager:
    global _instance
    if _instance is None:
        _instance = DatasetManager()
    return _instance
