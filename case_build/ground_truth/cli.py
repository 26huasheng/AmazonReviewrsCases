from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import GroundTruthPipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build GT1 / GT2 for selected SEMS cases")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--case-users", type=Path, required=True)
    p.add_argument("--case-shelf", type=Path, required=True)
    p.add_argument("--canonical-user-events", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--outcome-policy", default="first_observed_event")
    p.add_argument("--rating-daily-summary", type=Path)
    return p


def main() -> None:
    a = build_parser().parse_args()
    worker = GroundTruthPipeline(
        a.cases, a.case_users, a.case_shelf, a.canonical_user_events,
        a.output_dir, outcome_policy=a.outcome_policy,
        rating_daily_summary=a.rating_daily_summary,
    )
    try:
        result = worker.run()
    finally:
        worker.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
