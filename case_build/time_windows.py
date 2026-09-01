from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence

import duckdb

from .config import DEFAULT_TIME_BOXES
from utils import sql_literal


@dataclass(frozen=True)
class TimeBox:
    time_box_id: str
    start_date: date
    end_date: date


def _as_date(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        raise ValueError(f"{field} must be provided")
    return date.fromisoformat(str(value))


def parse_time_boxes(
    raw: Sequence[dict[str, Any]] | Sequence[TimeBox] | None = None,
) -> list[TimeBox]:
    source: Sequence[dict[str, Any]] | Sequence[TimeBox] = (
        DEFAULT_TIME_BOXES if raw is None else raw
    )
    if source and isinstance(source[0], TimeBox):
        boxes = list(source)  # type: ignore[arg-type]
    else:
        boxes = []
        seen: set[str] = set()
        for item in source:  # type: ignore[assignment]
            box_id = str(item.get("time_box_id") or "").strip()  # type: ignore[union-attr]
            if not box_id:
                raise ValueError("time_box_id must be non-empty")
            if box_id in seen:
                raise ValueError(f"duplicate time_box_id: {box_id}")
            seen.add(box_id)
            start = _as_date(item.get("start_date"), "start_date")  # type: ignore[union-attr]
            end = _as_date(item.get("end_date"), "end_date")  # type: ignore[union-attr]
            if start >= end:
                raise ValueError(f"{box_id}: start_date must be < end_date")
            boxes.append(TimeBox(box_id, start, end))
    ordered = sorted(boxes, key=lambda box: (box.start_date, box.time_box_id))
    for previous, current in zip(ordered, ordered[1:]):
        if current.start_date < previous.end_date:
            raise ValueError(
                f"overlapping time boxes: {previous.time_box_id} and {current.time_box_id}"
            )
    return ordered


def time_boxes_identity(boxes: Sequence[TimeBox]) -> list[dict[str, str]]:
    return [
        {
            "time_box_id": box.time_box_id,
            "start_date": box.start_date.isoformat(),
            "end_date": box.end_date.isoformat(),
        }
        for box in boxes
    ]


def attach_time_boxes(
    con: duckdb.DuckDBPyConnection,
    candidates_path: Path,
    destination: Path,
    boxes: Sequence[TimeBox],
    copy_atomic,
) -> int:
    """给 Case 候选加时间段标签；时间段只是属性，不再生成 market_segment。"""
    con.execute("DROP TABLE IF EXISTS case_time_boxes")
    con.execute("""
        CREATE TEMP TABLE case_time_boxes(
            time_box_id VARCHAR,
            start_date DATE,
            end_date DATE
        )
    """)
    if boxes:
        con.executemany(
            "INSERT INTO case_time_boxes VALUES (?, ?, ?)",
            [(box.time_box_id, box.start_date, box.end_date) for box in boxes],
        )
    source = sql_literal(str(candidates_path))
    copy_atomic(f"""
        SELECT c.*,
               b.time_box_id,
               b.start_date AS time_box_start_date,
               b.end_date AS time_box_end_date
        FROM read_parquet({source}) c
        LEFT JOIN case_time_boxes b
          ON c.t0 >= b.start_date
         AND c.t0 < b.end_date
    """, destination)
    outside = con.execute(
        f"SELECT count(*) FROM read_parquet({sql_literal(str(destination))}) "
        "WHERE time_box_id IS NULL"
    ).fetchone()[0]
    return int(outside)
