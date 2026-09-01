from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

import duckdb

from utils import sql_literal, write_json
from .eligibility import write_case_user_eligibility, write_threshold_scan
from .features import write_case_user_features
from .sampling import write_case_user_sample


class CasePopulationPipeline:
    """Market shared population → Case pre-t0 eligibility → fixed Case user sample."""

    def __init__(
        self,
        cases: Path,
        market_population: Path,
        user_history: Path,
        user_category_history: Path,
        user_market_history: Path,
        output_dir: Path,
        *,
        min_history_products: int | None = None,
        max_days_since_last_event: int | None = None,
        min_category_products: int | None = None,
        min_market_products: int | None = None,
        target_users_per_case: int | None = None,
        sampling_seed: str = "case_population_v1",
        history_scan_grid: Sequence[int] = (1, 3, 5, 10),
        recency_scan_grid: Sequence[int] = (90, 180, 365, 730),
    ) -> None:
        self.cases = cases.expanduser().resolve()
        self.market_population = market_population.expanduser().resolve()
        self.user_history = user_history.expanduser().resolve()
        self.user_category_history = user_category_history.expanduser().resolve()
        self.user_market_history = user_market_history.expanduser().resolve()
        self.output_dir = output_dir.expanduser().resolve()
        for path in (
            self.cases, self.market_population, self.user_history,
            self.user_category_history, self.user_market_history,
        ):
            if not path.is_file():
                raise FileNotFoundError(path)
        self.min_history_products = min_history_products
        self.max_days_since_last_event = max_days_since_last_event
        self.min_category_products = min_category_products
        self.min_market_products = min_market_products
        self.target_users_per_case = target_users_per_case
        self.sampling_seed = sampling_seed
        self.history_scan_grid = tuple(history_scan_grid)
        self.recency_scan_grid = tuple(recency_scan_grid)

        self.features_path = self.output_dir / "case_user_features.parquet"
        self.eligibility_path = self.output_dir / "case_user_eligibility.parquet"
        self.threshold_scan_path = self.output_dir / "population_threshold_scan.parquet"
        self.users_path = self.output_dir / "case_users.parquet"
        self.summary_path = self.output_dir / "case_population_summary.json"
        self.con = duckdb.connect()
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
        write_case_user_features(
            self.con,
            self.cases,
            self.market_population,
            self.user_history,
            self.user_category_history,
            self.user_market_history,
            self.features_path,
            self._copy_atomic,
        )
        write_threshold_scan(
            self.con,
            self.features_path,
            self.threshold_scan_path,
            self._copy_atomic,
            history_thresholds=self.history_scan_grid,
            recency_thresholds=self.recency_scan_grid,
        )
        write_case_user_eligibility(
            self.con,
            self.features_path,
            self.eligibility_path,
            self._copy_atomic,
            min_history_products=self.min_history_products,
            max_days_since_last_event=self.max_days_since_last_event,
            min_category_products=self.min_category_products,
            min_market_products=self.min_market_products,
        )
        write_case_user_sample(
            self.con,
            self.eligibility_path,
            self.users_path,
            self._copy_atomic,
            target_users_per_case=self.target_users_per_case,
            seed=self.sampling_seed,
        )
        payload = {
            "status": "COMPLETE",
            "schema_version": "case_population_v1",
            "case_count": int(self.con.execute(
                "SELECT count(DISTINCT case_candidate_id) FROM read_parquet(?)",
                [str(self.features_path)],
            ).fetchone()[0]),
            "feature_rows": int(self.con.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(self.features_path)]
            ).fetchone()[0]),
            "eligible_rows": int(self.con.execute(
                "SELECT count(*) FILTER (eligible_pre_t0) FROM read_parquet(?)",
                [str(self.eligibility_path)],
            ).fetchone()[0]),
            "selected_user_rows": int(self.con.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(self.users_path)]
            ).fetchone()[0]),
            "eligibility_policy": {
                "min_history_products": self.min_history_products,
                "max_days_since_last_event": self.max_days_since_last_event,
                "min_category_products": self.min_category_products,
                "min_market_products": self.min_market_products,
            },
            "target_users_per_case": self.target_users_per_case,
            "sampling_seed": self.sampling_seed,
            "future_data_used_for_selection": False,
        }
        write_json(self.summary_path, payload)
        return payload
