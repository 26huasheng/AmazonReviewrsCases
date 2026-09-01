from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import CasePopulationPipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build Case-level user population")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--market-population", type=Path, required=True)
    p.add_argument("--user-history", type=Path, required=True)
    p.add_argument("--user-category-history", type=Path, required=True)
    p.add_argument("--user-market-history", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--min-history-products", type=int)
    p.add_argument("--max-days-since-last-event", type=int)
    p.add_argument("--min-category-products", type=int)
    p.add_argument("--min-market-products", type=int)
    p.add_argument("--target-users-per-case", type=int)
    p.add_argument("--sampling-seed", default="case_population_v1")
    return p


def main() -> None:
    a = build_parser().parse_args()
    worker = CasePopulationPipeline(
        a.cases, a.market_population, a.user_history,
        a.user_category_history, a.user_market_history, a.output_dir,
        min_history_products=a.min_history_products,
        max_days_since_last_event=a.max_days_since_last_event,
        min_category_products=a.min_category_products,
        min_market_products=a.min_market_products,
        target_users_per_case=a.target_users_per_case,
        sampling_seed=a.sampling_seed,
    )
    try:
        result = worker.run()
    finally:
        worker.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
