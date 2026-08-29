from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable


T0_LO = "2022-08-01"
T0_HI = "2022-10-31"
MIN_POST90 = 50
ROUND2_MAX_TITLES = 96
DISCOVERY_SEED = "sems_path_market_discovery_v1"

ADAPTIVE_SAMPLE_TIERS = (
    (24, 24),
    (100, 24),
    (1_000, 32),
    (10_000, 48),
    (100_000, 64),
    (None, 96),
)


def adaptive_sample_size(path_product_count: int) -> int:
    if path_product_count < 0:
        raise ValueError("path_product_count cannot be negative")
    for upper, target in ADAPTIVE_SAMPLE_TIERS:
        if upper is None or path_product_count <= upper:
            return min(path_product_count, target)
    raise AssertionError("unreachable")


def _stable_digest(parts: Iterable[Any]) -> str:
    payload = json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_path_id(source_partition: str, category_path: list[str]) -> str:
    return "path_" + _stable_digest((source_partition, category_path))[:20]


def normalize_market_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower().strip()
    normalized = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE)
    return re.sub(r"_+", "_", normalized).strip("_")


def stable_local_market_id(path_id: str, market_label: str) -> str:
    label = normalize_market_label(market_label)
    return "local_" + _stable_digest((path_id, label))[:20]


def deterministic_rank(discovery_version: str, path_id: str, product_id: str) -> str:
    return _stable_digest((DISCOVERY_SEED, discovery_version, path_id, product_id))


def select_round1_sample(
    products: list[dict[str, Any]], discovery_version: str, path_id: str
) -> list[dict[str, Any]]:
    unique = {str(row["product_id"]): row for row in products}
    rows = list(unique.values())
    target = adaptive_sample_size(len(rows))
    ranked = sorted(
        rows,
        key=lambda row: deterministic_rank(discovery_version, path_id, str(row["product_id"])),
    )
    selected = ranked[:target]
    return [{**row, "sample_role": "sample"} for row in selected]


def normalize_title(value: str) -> tuple[str, list[str]]:
    normalized = unicodedata.normalize("NFKC", value).lower()
    normalized = "".join(character if character.isalnum() else " " for character in normalized)
    normalized = " ".join(normalized.split())
    return normalized, normalized.split() if normalized else []


def _term_tokens(term: str) -> tuple[str, ...]:
    return tuple(normalize_title(term)[1])


def phrase_spans(tokens: list[str], term: str) -> list[tuple[int, int]]:
    phrase = _term_tokens(term)
    if not phrase or len(phrase) > len(tokens):
        return []
    width = len(phrase)
    return [(index, index + width - 1) for index in range(len(tokens) - width + 1)
            if tuple(tokens[index:index + width]) == phrase]


@dataclass(frozen=True)
class MarketRule:
    local_market_id: str
    market_label: str
    center_term: str
    equivalent_terms: tuple[str, ...]
    support_terms: tuple[str, ...]
    confidence: float | None = None


# Fixed scoring contract.
ASSIGN_THRESHOLD = 4
MARGIN_THRESHOLD = 2
IDENTITY_SCORE = 4
SUPPORT_HIT_SCORE = 1
SUPPORT_MAX_SCORE = 3
SUPPORT_MAX_HITS = 3


def _identity_hits(tokens: list[str], rule: MarketRule) -> tuple[str | None, list[str]]:
    """Identity group: center_term plus equivalent_terms.

    Any single hit grants the whole identity group (IDENTITY_SCORE), never one
    per matched term, and never more than IDENTITY_SCORE in total.
    """
    center: str | None = None
    equivalents: list[str] = []
    if rule.center_term and phrase_spans(tokens, rule.center_term):
        center = rule.center_term
    for term in rule.equivalent_terms:
        if phrase_spans(tokens, term):
            equivalents.append(term)
    return center, equivalents


def _match_support_terms(tokens: list[str], support_terms: tuple[str, ...]) -> list[str]:
    """Support hits with deterministic overlap dedup.

    Terms are matched as phrases; overlapping spans count once.  When two terms
    cover the same text span (e.g. ``ram`` and ``8gb ram`` on "8GB RAM"), the
    longer/more specific phrase wins and only one support hit is counted.
    """
    if not support_terms:
        return []
    hits: list[tuple[str, tuple[int, int]]] = []
    for term in support_terms:
        for span in phrase_spans(tokens, term):
            hits.append((term, span))
    # Longer phrases first: the most specific expression of the same span wins.
    hits.sort(key=lambda item: (item[1][1] - item[1][0], len(item[0])), reverse=True)
    occupied: list[tuple[int, int]] = []
    matched: list[str] = []
    for term, (start, end) in hits:
        if any(start <= right and left <= end for left, right in occupied):
            continue
        occupied.append((start, end))
        matched.append(term)
    return sorted(set(matched))


def score_market(tokens: list[str], rule: MarketRule) -> dict[str, Any]:
    """Fixed 0..7 score for one market rule.

    identity_score = 0 or 4 (whole identity group, at most once)
    support_score   = min(distinct support hits, 3) * 1
    """
    center, equivalents = _identity_hits(tokens, rule)
    identity = IDENTITY_SCORE if (center is not None or equivalents) else 0
    support = _match_support_terms(tokens, rule.support_terms)[:SUPPORT_MAX_HITS]
    support_score = len(support) * SUPPORT_HIT_SCORE
    return {
        "identity": identity,
        "support_hits": support,
        "support_score": support_score,
        "total": identity + support_score,
    }


def classify_title(title: str, rules: list[MarketRule],
                   threshold: int = ASSIGN_THRESHOLD,
                   margin: int = MARGIN_THRESHOLD) -> dict[str, Any]:
    """Assign a title to at most one market using the fixed scoring contract.

    - No market reaches `threshold`           -> UNMATCHED (weak audit kept)
    - Exactly one market reaches `threshold`  -> ASSIGNED to it
    - Top two both reach `threshold` and top1 - top2 < margin -> AMBIGUOUS
    - Otherwise                                -> ASSIGNED to top1
    """
    _, tokens = normalize_title(title)
    evaluations: list[tuple[MarketRule, dict[str, Any]]] = []
    for rule in rules:
        score = score_market(tokens, rule)
        if score["total"] > 0:
            evaluations.append((rule, score))
    evaluations.sort(key=lambda item: (item[1]["total"], item[0].market_label), reverse=True)
    matched_center: str | None = None
    matched_equivalents: list[str] = []
    matched_support: list[str] = []
    for rule, score in evaluations:
        center, equivalents = _identity_hits(tokens, rule)
        if center and matched_center is None:
            matched_center = center
        for term in equivalents:
            if term not in matched_equivalents:
                matched_equivalents.append(term)
        for term in score["support_hits"]:
            if term not in matched_support:
                matched_support.append(term)
    matched_equivalents.sort()
    matched_support.sort()

    if not evaluations:
        return {
            "assignment_status": "UNMATCHED", "local_market_id": None,
            "market_label": None, "candidate_local_market_ids": [],
            "candidate_market_labels": [], "top_score": 0, "second_score": 0,
            "matched_center_term": None, "matched_equivalent_terms": [],
            "matched_support_terms": [],
            "ambiguous_llm_used": False, "ambiguous_llm_selected_market": None,
        }

    top_rule, top_score = evaluations[0]
    second_score = evaluations[1][1]["total"] if len(evaluations) > 1 else 0
    candidates = [(rule, score["total"]) for rule, score in evaluations
                  if score["total"] >= threshold]
    if top_score["total"] < threshold:
        return {
            "assignment_status": "UNMATCHED", "local_market_id": None,
            "market_label": None,
            "candidate_local_market_ids": [rule.local_market_id for rule, _ in candidates],
            "candidate_market_labels": [rule.market_label for rule, _ in candidates],
            "top_score": top_score["total"], "second_score": second_score,
            "matched_center_term": matched_center, "matched_equivalent_terms": matched_equivalents,
            "matched_support_terms": matched_support,
            "ambiguous_llm_used": False, "ambiguous_llm_selected_market": None,
        }
    competing = [(rule, score["total"]) for rule, score in evaluations
                 if score["total"] >= threshold and top_score["total"] - score["total"] < margin]
    if len(competing) > 1:
        competing.sort(key=lambda item: (item[1], item[0].market_label), reverse=True)
        return {
            "assignment_status": "AMBIGUOUS", "local_market_id": None,
            "market_label": None,
            "candidate_local_market_ids": [rule.local_market_id for rule, _ in competing],
            "candidate_market_labels": [rule.market_label for rule, _ in competing],
            "top_score": top_score["total"], "second_score": second_score,
            "matched_center_term": matched_center, "matched_equivalent_terms": matched_equivalents,
            "matched_support_terms": matched_support,
            "ambiguous_llm_used": False, "ambiguous_llm_selected_market": None,
        }
    return {
        "assignment_status": "ASSIGNED",
        "local_market_id": top_rule.local_market_id,
        "market_label": top_rule.market_label,
        "candidate_local_market_ids": [rule.local_market_id for rule, _ in candidates],
        "candidate_market_labels": [rule.market_label for rule, _ in candidates],
        "top_score": top_score["total"], "second_score": second_score,
        "matched_center_term": matched_center, "matched_equivalent_terms": matched_equivalents,
        "matched_support_terms": matched_support,
        "ambiguous_llm_used": False, "ambiguous_llm_selected_market": None,
    }


def select_round2_sample(
    groups: dict[str, list[dict[str, Any]]], discovery_version: str, path_id: str,
    limit: int = ROUND2_MAX_TITLES,
) -> list[dict[str, Any]]:
    ranked = {
        group: sorted(rows, key=lambda row: deterministic_rank(
            discovery_version, path_id + ":round2:" + group, str(row["product_id"])
        )) for group, rows in sorted(groups.items()) if rows
    }
    selected: list[dict[str, Any]] = []
    depth = 0
    while len(selected) < limit and any(depth < len(rows) for rows in ranked.values()):
        for group, rows in ranked.items():
            if depth < len(rows) and len(selected) < limit:
                selected.append({**rows[depth], "provisional_group": group})
        depth += 1
    return selected


def validate_llm_response(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"decision", "markets"}:
        raise ValueError("response must contain exactly decision and markets")
    decision = value.get("decision")
    if decision not in {"KEEP", "SPLIT", "REVIEW"}:
        raise ValueError("decision must be KEEP, SPLIT, or REVIEW")
    markets = value.get("markets")
    if not isinstance(markets, list):
        raise ValueError("markets must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for market in markets:
        if not isinstance(market, dict):
            raise ValueError("each market must be an object")
        required = {"market_label", "center_term", "equivalent_terms", "support_terms", "confidence"}
        if set(market) != required:
            raise ValueError("market object has missing or unknown fields")
        if not isinstance(market["market_label"], str):
            raise ValueError("market_label must be a string")
        center = str(market["center_term"] or "").strip()
        if not center:
            raise ValueError("center_term must be exactly one non-empty term")
        for field in ("equivalent_terms", "support_terms"):
            if not isinstance(market[field], list) or any(not isinstance(term, str) for term in market[field]):
                raise ValueError(f"{field} must be an array of strings")
        if isinstance(market["confidence"], bool) or not isinstance(market["confidence"], (int, float)):
            raise ValueError("confidence must be numeric")
        label = normalize_market_label(str(market.get("market_label", "")))
        if not label or label in seen:
            raise ValueError("market_label must be non-empty and unique after normalization")
        seen.add(label)
        equivalent = [str(term).strip() for term in market.get("equivalent_terms", []) if str(term).strip()]
        support = [str(term).strip() for term in market.get("support_terms", []) if str(term).strip()]
        if len(equivalent) > 20 or len(support) > 40:
            raise ValueError("market term counts violate the discovery contract")
        confidence = float(market["confidence"])
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        normalized.append({"market_label": label, "center_term": center,
                           "equivalent_terms": equivalent, "support_terms": support,
                           "confidence": confidence})
    if decision == "KEEP" and len(normalized) != 1:
        raise ValueError("KEEP requires exactly one market")
    if decision == "SPLIT" and len(normalized) < 2:
        raise ValueError("SPLIT requires at least two markets")
    if decision == "REVIEW" and normalized:
        raise ValueError("REVIEW requires an empty markets list")
    return {"decision": decision, "markets": normalized}


def validate_arbitration_response(value: dict[str, Any], candidates: list[str]) -> str | None:
    """Validate the lightweight AMBIGUOUS arbitration response.

    The LLM must select one of the given candidate market labels or null.
    """
    if not isinstance(value, dict) or set(value) != {"selected_market"}:
        raise ValueError("arbitration response must contain exactly selected_market")
    selected = value.get("selected_market")
    if selected is None:
        return None
    if not isinstance(selected, str):
        raise ValueError("selected_market must be a string or null")
    chosen = normalize_market_label(selected)
    candidates_normalized = [normalize_market_label(item) for item in candidates]
    if chosen not in candidates_normalized:
        raise ValueError(f"selected_market {chosen!r} is not one of the candidates")
    return candidates[candidates_normalized.index(chosen)]
