from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import CaseQualityPipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Aggregate Case quality signals and apply gate")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--case-shelf", type=Path, required=True)
    p.add_argument("--case-users", type=Path, required=True)
    p.add_argument("--choice-truth", type=Path, required=True)
    p.add_argument("--population-truth", type=Path, required=True)
    p.add_argument("--market-truth", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--rules-json", type=Path)
    p.add_argument("--review-activity-truth", type=Path)
    p.add_argument("--external-signals", type=Path)
    return p


def main() -> None:
    a = build_parser().parse_args()
    worker = CaseQualityPipeline(
        a.cases, a.case_shelf, a.case_users, a.choice_truth,
        a.population_truth, a.market_truth, a.output_dir,
        rules_json=a.rules_json,
        review_activity_truth=a.review_activity_truth,
        external_signals=a.external_signals,
    )
    try:
        result = worker.run()
    finally:
        worker.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
