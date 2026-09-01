from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scan import PopulationScanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan category-level Amazon user population")
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-partition", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    worker = PopulationScanner(
        args.events,
        args.output_dir,
        source_partition=args.source_partition,
    )
    try:
        summary = worker.run()
    finally:
        worker.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
