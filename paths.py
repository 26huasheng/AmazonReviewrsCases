from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
# Compatibility name retained for code moved from AmazonReviewrepo/v5.
PIPELINE_DIR = REPO_ROOT


def workspace_root(pipeline_dir: Path = PIPELINE_DIR) -> Path:
    """Return the standalone AmazonReviewrsCases repository root."""
    return pipeline_dir.expanduser().resolve()


def resolve_existing(root: Path, relative: str) -> Path:
    """Prefer a path inside this repository, then the repository's parent workspace."""
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
    return resolve_existing(workspace_root(pipeline_dir), "self-evolving-market-simulation")


def default_output_root(pipeline_dir: Path = PIPELINE_DIR) -> Path:
    return workspace_root(pipeline_dir) / "outputs"
