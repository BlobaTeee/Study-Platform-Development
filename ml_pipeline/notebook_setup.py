"""Bootstrap import paths and seeds for the pipeline notebooks."""
from __future__ import annotations

import random
import sys

import numpy as np

from . import config


def bootstrap() -> None:
    if str(config.REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(config.REPO_ROOT))
    random.seed(config.RANDOM_SEED)
    np.random.seed(config.RANDOM_SEED)
