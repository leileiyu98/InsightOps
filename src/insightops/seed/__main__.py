"""Command-line lifecycle for the M1.2A deterministic dataset."""

import argparse
import json
from pathlib import Path

from insightops.core.config import load_settings
from insightops.db.session import create_database_engine
from insightops.seed.dataset import load_seed_dataset
from insightops.seed.loader import DatasetLoader

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "data" / "seed" / "m1_2a"


def main() -> None:
    """Run a deterministic dataset lifecycle command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("digest", "load", "verify", "unload"))
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
    )
    args = parser.parse_args()

    dataset = load_seed_dataset(args.dataset_root)
    if args.command == "digest":
        print(dataset.computed_digest)
        return

    settings = load_settings()
    engine = create_database_engine(settings)
    try:
        loader = DatasetLoader(engine, dataset, app_env=settings.app_env)
        operation = getattr(loader, args.command)
        counts = operation()
    finally:
        engine.dispose()

    print(
        json.dumps(
            {
                "command": args.command,
                "dataset_id": dataset.manifest.dataset_id,
                "dataset_version": dataset.manifest.dataset_version,
                "dataset_digest": dataset.computed_digest,
                "row_counts": counts,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
