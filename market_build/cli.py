from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import MarketBuildPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build reusable Market-level assets")
    parser.add_argument("--final-market", type=Path, required=True)
    parser.add_argument("--product-core", type=Path, required=True)
    parser.add_argument("--user-events", type=Path, required=True)
    parser.add_argument("--user-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--product-time-summary", type=Path)
    parser.add_argument("--fallback-source-partition")
    parser.add_argument("--population-source", choices=["category", "global"], default="category")
    parser.add_argument("--population-size", type=int)
    parser.add_argument("--population-seed", default="market_population_v1")
    parser.add_argument("--user-bucket-count", type=int, default=256)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    worker = MarketBuildPipeline(
        args.final_market,
        args.product_core,
        args.user_events,
        args.user_summary,
        args.output_dir,
        product_time_summary=args.product_time_summary,
        fallback_source_partition=args.fallback_source_partition,
        population_source=args.population_source,
        population_size=args.population_size,
        population_seed=args.population_seed,
        user_bucket_count=args.user_bucket_count,
    )
    try:
        result = worker.run()
    finally:
        worker.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
