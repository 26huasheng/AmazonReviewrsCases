from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format=LOG_FORMAT)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


# Rows failing any of these are dropped from product_core before Market Discovery.
PRODUCT_CORE_KEEP_PREDICATE = """
product_id IS NOT NULL AND trim(CAST(product_id AS VARCHAR)) <> ''
AND product_title IS NOT NULL AND trim(product_title) <> ''
AND category_path IS NOT NULL AND len(category_path) > 0
"""


def parsed_first_available_sql(expr: str) -> str:
    """Parse Amazon metadata Date First Available into DATE; NULL if unparseable."""
    return (
        f"coalesce("
        f"TRY_CAST({expr} AS DATE), "
        f"try_strptime({expr}, '%Y-%m-%d')::DATE, "
        f"try_strptime({expr}, '%B %-d, %Y')::DATE, "
        f"try_strptime({expr}, '%B %d, %Y')::DATE, "
        f"try_strptime({expr}, '%b %-d, %Y')::DATE, "
        f"try_strptime({expr}, '%b %d, %Y')::DATE)"
    )


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
