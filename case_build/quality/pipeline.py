from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb

from utils import sql_literal, write_json
from .metrics import write_quality_metrics
from .rules import load_quality_rules, write_quality_decisions


class CaseQualityPipeline:
    """汇总 Case 质量信号，并用显式配置执行最终 acceptance gate。"""

    def __init__(
        self,
        cases: Path,
        case_shelf: Path,
        case_users: Path,
        choice_truth: Path,
        population_truth: Path,
        market_truth: Path,
        output_dir: Path,
        *,
        rules_json: Path | None = None,
        review_activity_truth: Path | None = None,
        external_signals: Path | None = None,
    ) -> None:
        self.cases = cases.expanduser().resolve()
        self.case_shelf = case_shelf.expanduser().resolve()
        self.case_users = case_users.expanduser().resolve()
        self.choice_truth = choice_truth.expanduser().resolve()
        self.population_truth = population_truth.expanduser().resolve()
        self.market_truth = market_truth.expanduser().resolve()
        self.output_dir = output_dir.expanduser().resolve()
        self.rules_json = rules_json.expanduser().resolve() if rules_json else None
        self.review_activity_truth = (
            review_activity_truth.expanduser().resolve()
            if review_activity_truth else None
        )
        self.external_signals = (
            external_signals.expanduser().resolve() if external_signals else None
        )
        for path in (
            self.cases, self.case_shelf, self.case_users,
            self.choice_truth, self.population_truth, self.market_truth,
        ):
            if not path.is_file():
                raise FileNotFoundError(path)
        for path in (self.rules_json, self.review_activity_truth, self.external_signals):
            if path is not None and not path.is_file():
                raise FileNotFoundError(path)

        self.work_dir = self.output_dir / "_work"
        self.base_metrics_path = self.work_dir / "quality_metrics_base.parquet"
        self.metrics_path = self.output_dir / "quality_metrics.parquet"
        self.decisions_path = self.output_dir / "quality_decisions.parquet"
        self.accepted_cases_path = self.output_dir / "accepted_cases.parquet"
        self.rejected_cases_path = self.output_dir / "rejected_cases.parquet"
        self.summary_path = self.output_dir / "quality_summary.json"

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
        self.work_dir.mkdir(parents=True, exist_ok=True)
        write_quality_metrics(
            self.con,
            self.cases,
            self.case_shelf,
            self.case_users,
            self.choice_truth,
            self.population_truth,
            self.market_truth,
            self.base_metrics_path,
            self._copy_atomic,
            review_activity_truth=self.review_activity_truth,
        )
        if self.external_signals is not None:
            base = sql_literal(str(self.base_metrics_path))
            ext = sql_literal(str(self.external_signals))
            self._copy_atomic(f"""
                SELECT m.*, e.* EXCLUDE(case_candidate_id)
                FROM read_parquet({base}) m
                LEFT JOIN read_parquet({ext}) e USING(case_candidate_id)
            """, self.metrics_path)
            external_status = "MERGED"
        else:
            self._copy_atomic(
                f"SELECT * FROM read_parquet({sql_literal(str(self.base_metrics_path))})",
                self.metrics_path,
            )
            external_status = "NOT_PROVIDED"

        rules = load_quality_rules(self.rules_json)
        write_quality_decisions(
            self.con,
            self.metrics_path,
            self.decisions_path,
            self._copy_atomic,
            rules=rules,
        )
        self._copy_atomic(f"""
            SELECT * FROM read_parquet({sql_literal(str(self.decisions_path))})
            WHERE quality_pass
        """, self.accepted_cases_path)
        self._copy_atomic(f"""
            SELECT * FROM read_parquet({sql_literal(str(self.decisions_path))})
            WHERE NOT quality_pass
        """, self.rejected_cases_path)

        payload = {
            "status": "COMPLETE",
            "schema_version": "case_quality_v1",
            "rules": rules,
            "external_signals_status": external_status,
            "candidate_case_count": int(self.con.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(self.decisions_path)]
            ).fetchone()[0]),
            "accepted_case_count": int(self.con.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(self.accepted_cases_path)]
            ).fetchone()[0]),
            "rejected_case_count": int(self.con.execute(
                "SELECT count(*) FROM read_parquet(?)", [str(self.rejected_cases_path)]
            ).fetchone()[0]),
        }
        write_json(self.summary_path, payload)
        return payload
