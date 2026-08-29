from __future__ import annotations

from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parent.parent


def workspace_root(pipeline_dir: Path = PIPELINE_DIR) -> Path:
    """Resolve both `<repo>/scripts/sems_market_pipeline` and portable layouts."""
    candidate = pipeline_dir.parents[1]
    return candidate if (candidate / "scripts/sems_market_pipeline").resolve() == pipeline_dir.resolve() else pipeline_dir.parent


def resolve_existing(root: Path, relative: str) -> Path:
    """Prefer a path inside the workspace; otherwise use the sibling directory if it exists."""
    inside = root / relative
    if inside.exists():
        return inside
    sibling = root.parent / relative
    if sibling.exists():
        return sibling
    return inside


def default_data_root(pipeline_dir: Path = PIPELINE_DIR) -> Path:
    return resolve_existing(workspace_root(pipeline_dir), "data/reviews2023")


def default_reference_repo(pipeline_dir: Path = PIPELINE_DIR) -> Path:
    bundled = pipeline_dir / "reference_contract"
    if bundled.is_dir():
        return bundled
    return resolve_existing(workspace_root(pipeline_dir), "self-evolving-market-simulation")


def default_output_root(pipeline_dir: Path = PIPELINE_DIR) -> Path:
    return resolve_existing(workspace_root(pipeline_dir), "outputs")
