#!/usr/bin/env python3
"""Rebuild final_market from an existing first_market without any LLM calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cross_path_merge import merge_exact_normalized_markets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge cross-path markets only when market labels are equal after "
            "safe formatting normalization. No LLM calls are made."
        )
    )
    parser.add_argument(
        "--discovery-dir",
        required=True,
        type=Path,
        help="Directory containing first_market.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = merge_exact_normalized_markets(args.discovery_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
