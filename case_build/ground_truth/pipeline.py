from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb

from utils import sql_literal, write_json
from .future_events import write_case_future_market_events, write_review_activity_truth
from .outcome import write_positive_user_outcomes
from .tables import write_choice_truth, write_market_truth, write_population_truth


class GroundTruthPipeline:
    """固定 Case 用户后再查询 future，生成 GT1 / GT2 / 商品级聚合。"""

    def __init__(
        self,
        cases: Path,
        case_users: Path,
        case_shelf: Path,
        canonical_user_events: Path,
        output_dir: Path,
        *,
        outcome_policy: str = "first_observed_event",
        rating_daily_summary: Path | None = None,
    ) -> None:
        self.cases = cases.expanduser().resolve()
        self.case_users = case_users.expanduser().resolve()
        self.case_shelf = case_shelf.expanduser().resolve()
        self.canonical_user_events = canonical_user_events.expanduser().resolve()
        self.output_dir = output_dir.expanduser().resolve()
        self.outcome_policy = outcome_policy
        self.rating_daily_summary = (
            rating_daily_summary.expanduser().resolve()
            if rating_daily_summary else None
        )
        for path in (self.cases, self.case_users, self.case_shelf, self.canonical_user_events):
            if not path.is_file():
                raise FileNotFoundError(path)
        if self.rating_daily_summary is not None and not self.rating_daily_summary.is_file():
            raise FileNotFoundError(self.rating_daily_summary)

        self.work_dir = self.output_dir / "_work"
        self.future_events_path = self.work_dir / "future_market_events.parquet"
        self.positive_outcomes_path = self.work_dir / "positive_user_outcomes.parquet"
        self.choice_truth_path = self.output_dir / "choice_truth.parquet"
        self.population_truth_path = self.output_dir / "population_truth.parquet"
        self.market_truth_path = self.output_dir / "market_truth.parquet"
        self.review_activity_truth_path = self.output_dir / "review_activity_truth.parquet"
        self.summary_path = self.output_dir / "ground_truth_summary.json"

        self.con = duckdb.connect()
        self.con.execute("SET TimeZone='UTC'")
        self.con.execute("SET preserve_insertion_order=false")
        temp = self.output_dir / ".duckdb_tmp"
        temp.mkdir(parents=True, exist_ok=True)
        self.con.execute(f"SET temp_directory={sql_literal(str(temp))}")

    def close(self) -> None:
        self.con.close()

    def _copy_atomic(self, query: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + ".part")
        part.unlink(missing_ok=True)
        self.con.execute(
            f"COPY ({query}) TO {sql_literal(str(part))} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        os.replace(part, path)

    def run(self) -> dict[str, Any]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        write_case_future_market_events(
            self.con, self.cases, self.case_users, self.case_shelf,
            self.canonical_user_events, self.future_events_path, self._copy_atomic,
        )
        write_positive_user_outcomes(
            self.con, self.future_events_path, self.positive_outcomes_path,
            self._copy_atomic, outcome_policy=self.outcome_policy,
        )
        write_population_truth(
            self.con, self.case_users, self.positive_outcomes_path,
            self.population_truth_path, self._copy_atomic,
        )
        write_choice_truth(
            self.con, self.population_truth_path,
            self.choice_truth_path, self._copy_atomic,
        )
        write_market_truth(
            self.con, self.case_shelf, self.population_truth_path,
            self.market_truth_path, self._copy_atomic,
        )
        review_activity_status = "NOT_PROVIDED"
        if self.rating_daily_summary is not None:
            write_review_activity_truth(
                self.con, self.cases, self.case_shelf, self.rating_daily_summary,
                self.review_activity_truth_path, self._copy_atomic,
            )
            review_activity_status = "COMPUTED"

        payload = {
            "status": "COMPLETE",
            "schema_version": "ground_truth_v1",
            "outcome_policy": self.outcome_policy,
            "case_user_rows": int(self.con.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(self.case_users)]
            ).fetchone()[0]),
            "future_market_event_rows": int(self.con.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(self.future_events_path)]
            ).fetchone()[0]),
            "gt1_rows": int(self.con.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(self.choice_truth_path)]
            ).fetchone()[0]),
            "gt2_rows": int(self.con.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(self.population_truth_path)]
            ).fetchone()[0]),
            "review_activity_truth_status": review_activity_status,
            "population_was_fixed_before_future_lookup": True,
        }
        write_json(self.summary_path, payload)
        return payload
