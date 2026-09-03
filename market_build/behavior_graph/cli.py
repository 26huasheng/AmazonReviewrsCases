from __future__ import annotations

import argparse
from pathlib import Path

from .config import BehaviorGraphRules
from .pipeline import BehaviorGraphBuildPipeline, BehaviorGraphCasePipeline


def _rules(args: argparse.Namespace) -> BehaviorGraphRules:
    return BehaviorGraphRules(
        min_endpoint_users=args.min_endpoint_users,
        min_shared_users=args.min_shared_users,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SEMS behavior graph builder")
    sub = parser.add_subparsers(dest="command", required=True)

    full = sub.add_parser(
        "build",
        help="build full-period audit graph and pre-t0 cumulative indexes",
    )
    full.add_argument("--canonical-user-events", type=Path, required=True)
    full.add_argument("--market-products", type=Path, required=True)
    full.add_argument("--output-dir", type=Path, required=True)
    full.add_argument("--min-endpoint-users", type=int, default=100)
    full.add_argument("--min-shared-users", type=int, default=5)

    case = sub.add_parser(
        "case",
        help="attach strict pre-t0 graph relations to an existing case shelf",
    )
    case.add_argument("--case-shelf", type=Path, required=True)
    case.add_argument("--market-products", type=Path, required=True)
    case.add_argument("--product-user-cumulative", type=Path, required=True)
    case.add_argument("--pair-cumulative", type=Path, required=True)
    case.add_argument("--output-dir", type=Path, required=True)
    case.add_argument("--min-endpoint-users", type=int, default=100)
    case.add_argument("--min-shared-users", type=int, default=5)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "build":
        pipeline = BehaviorGraphBuildPipeline(
            args.canonical_user_events,
            args.market_products,
            args.output_dir,
            rules=_rules(args),
        )
    else:
        pipeline = BehaviorGraphCasePipeline(
            args.case_shelf,
            args.market_products,
            args.product_user_cumulative,
            args.pair_cumulative,
            args.output_dir,
            rules=_rules(args),
        )

    try:
        payload = pipeline.run()
        print(payload)
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
