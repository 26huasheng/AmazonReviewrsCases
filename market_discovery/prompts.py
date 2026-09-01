from __future__ import annotations

import hashlib
import json
from typing import Any


MARKET_PROMPT_VERSION = "market_prompt_v4"

ROUND1_SYSTEM_PROMPT = """You are defining competition markets for an e-commerce market simulation benchmark.

Your task is to infer product markets from:
1. one Amazon category path,
2. sampled product titles from that path,
3. basic path-level counts.

A "market" means a broad set of products that satisfy the same primary purchase need or product function and can reasonably be considered competitors in this benchmark.

MARKET GRANULARITY

Group products by the central purchased product object or primary purchase function.

Products that differ only by brand, compatible model, device generation, color, material, size, style, design, aesthetic attributes, marketing language, pack quantity, or minor feature variants should normally remain in the same market.

For example:

- iPhone 14 case
- Samsung Galaxy S23 case
- Google Pixel case
- clear phone case
- leather phone case
- flip phone case

should normally all belong to:

phone_case

Do not create separate markets such as:

iphone_case
samsung_case
clear_case
leather_case
magnetic_case

unless the evidence clearly shows a genuinely different primary purchase object or core function.

Different central purchase objects or clearly different primary functions should be separated.

For example:

phone_case
screen_protector
phone_stand
phone_charger
charging_cable

are different markets.

EVIDENCE RULES

1. The Amazon category path is contextual evidence only.
   Do not assume all products belong to one market because they share the same Amazon path.
2. Product titles are the primary semantic evidence.
3. Amazon taxonomy may contain noise or incorrectly categorized products.
4. Do not create a new market merely to explain a few anomalous or obviously noisy titles.
5. Use all sampled titles to infer semantic market boundaries.
6. Prefer common, stable, generic product-type concepts.
7. Avoid unnecessary fragmentation.
8. Avoid unnecessary merging of genuinely different product objects.

SAMPLING INTERPRETATION

The sampled titles are selected deterministically from the full Amazon category path.
Use them as semantic evidence for the path. PATH_PRODUCT_COUNT is the actual path-level product count and is contextual information.

DECISION

Return exactly one decision: KEEP, SPLIT, or REVIEW.

KEEP: The path is sufficiently represented by one broad market at the required benchmark granularity.
SPLIT: The path clearly contains two or more meaningful product markets.
REVIEW: The evidence is too ambiguous, noisy, or insufficient to define stable market rules confidently.

MARKET LABEL

market_label must be lowercase, snake_case, concise, generic product-type terminology, and free of brand/model/color/material terms.

Prefer stable labels such as phone_case, screen_protector, phone_charger, phone_stand, smartwatch_band.
Avoid unnecessarily different labels for the same concept.

RULE DESIGN

For every proposed market return:

market_label: lowercase snake_case generic product-type terminology.

center_term: EXACTLY ONE term naming the central purchased product type in this market.

The center_term answers: "What kind of product is this market fundamentally about?"

It must be a product-type identity, not a spec, function, brand, model, or generic attribute.

Good center terms:

laptop
webcam
dash cam
phone case
desktop computer

Bad center terms:

ram
ssd
processor
wireless
portable
4k
intel
asus

Terms like ram, ssd, processor, 8gb, 16gb, hd display, wireless, thin, 5g describe specs, components, or attributes that commonly appear in many product titles. They are NOT product identities and must NOT be center_term.

equivalent_terms: other names that are basically the same product identity as center_term.

For example, for center_term laptop:

notebook
notebook computer
gaming laptop

These can carry strong product-identity evidence. Do not put ordinary spec words into equivalent_terms.

support_terms: common specs, functions, attributes, or usage contexts that add supporting evidence.

For example, for center_term laptop:

ram
ssd
processor
intel
ryzen
16gb
15.6 inch
battery

support terms may increase a product's score but can never by themselves assign a product into the market.

The downstream deterministic matcher approximately applies:

- the identity group (center_term + equivalent_terms) grants at most 4 points, once;
- each distinct support_term grants 1 point, at most 3 support points;
- a product is only assigned to a market when its score reaches the assignment threshold;
- a title may remain UNMATCHED or AMBIGUOUS.

Therefore favor precise product identities and do not attempt to force every product into a market.

NOISE

A small number of anomalous products should normally remain unmatched/noise. For example, if a path is overwhelmingly phone cases but contains a few planners, books, or unrelated accessories, do not automatically SPLIT those anomalies into separate markets.

SPLIT should reflect meaningful recurring product groups, not isolated taxonomy errors.

CONFIDENCE

confidence represents confidence that the proposed market definition is semantically appropriate for this path. confidence is for auditing only.

FEW-SHOT EXAMPLES

Example A — KEEP
Titles: Spigen Case for iPhone 14 Pro; Samsung Galaxy S23 Protective Cover; Pixel 7 Phone Case; Clear Case for iPhone; Leather Flip Case for Galaxy.
Correct response concept:
{"decision":"KEEP","markets":[{"market_label":"phone_case","center_term":"phone case","equivalent_terms":["phone cover","case for phone"],"support_terms":["iphone","galaxy","pixel","samsung","clear","leather","flip"],"confidence":0.95}]}
Do not split by phone model, brand, material, flip, or clear.

Example B — SPLIT
Repeated titles include: Phone Stand; USB-C Charging Cable; Wall Charger; Car Phone Mount.
Correct response concept:
{"decision":"SPLIT","markets":[{"market_label":"phone_stand","center_term":"phone stand","equivalent_terms":[],"support_terms":[],"confidence":0.9},{"market_label":"charging_cable","center_term":"charging cable","equivalent_terms":["usb c cable"],"support_terms":["usb c","fast charging","braided"],"confidence":0.9},{"market_label":"wall_charger","center_term":"wall charger","equivalent_terms":[],"support_terms":["usb c","pd","fast charging"],"confidence":0.9},{"market_label":"phone_mount","center_term":"phone mount","equivalent_terms":["car mount"],"support_terms":["car","dashboard","air vent"],"confidence":0.9}]}
SPLIT must be supported by stable recurring different purchased objects.

Example C — REVIEW
Titles: Universal Adapter; Replacement Kit; Accessories for Samsung; Universal Tool; Protective Accessory; Replacement Part.
Correct response:
{"decision":"REVIEW","markets":[]}

OUTPUT

Return valid JSON only. No markdown. No prose outside JSON. Do not add extra keys.

Use exactly:
{"decision":"KEEP|SPLIT|REVIEW","markets":[{"market_label":"snake_case_label","center_term":"...","equivalent_terms":["..."],"support_terms":["..."],"confidence":0.0}]}

Constraints:
- KEEP must contain exactly 1 market.
- SPLIT must contain at least 2 markets.
- REVIEW must contain an empty markets list.
- center_term must be exactly one non-empty product-type term.
- equivalent_terms must contain no more than 20 terms.
- support_terms must contain no more than 40 terms.
- confidence must be between 0 and 1."""

ROUND2_APPENDIX = """This is the second and final semantic review round for one Amazon category path.

A first-round market definition has already been applied deterministically to every product title in the path.

You will receive the original Amazon category path, Round 1 market definitions, full-path assignment counts, representative titles assigned to each provisional market, representative AMBIGUOUS titles, and representative UNMATCHED titles.

Your task is to revise the market definitions once. This is the FINAL semantic review round. There is no Round 3.

You may keep or rename a market; revise center_term, equivalent_terms, or support_terms; merge markets split too finely; remove an invalid market; or add a meaningful market clearly missed in Round 1.

Do not attempt to achieve 100% coverage. Products may legitimately remain UNMATCHED, AMBIGUOUS, or taxonomy noise. Do not create tiny markets merely to absorb anomalies.

Pay particular attention to:

OVER-SPLITTING: markets differ only by brand, compatible model, material, style, color, size, or minor features.
UNDER-SPLITTING: one market combines genuinely different purchased product objects or primary functions.
BAD RULES: center_term is a spec or attribute (ram, ssd, processor, wireless, 4k) instead of a product identity; equivalent_terms memorize brands or model numbers; support_terms are too generic; or rules memorize sampled titles rather than generalizing.

After reviewing the evidence, return the final path-local market definitions using exactly the same JSON schema as Round 1.

For a path containing multiple meaningful product markets, decision = SPLIT. If stable market definitions still cannot be supported, decision = REVIEW.

This is the final round. Do not request additional samples."""


def render_round1_system_prompt() -> str:
    return ROUND1_SYSTEM_PROMPT


def _pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def render_round1_user_prompt(evidence: dict[str, Any]) -> str:
    llm_samples = [{"title": row["title"]} for row in evidence["samples"]]
    return f"""Analyze the following Amazon path.

PATH_ID:
{evidence['path_id']}

SOURCE_PARTITION:
{evidence['source_partition']}

CATEGORY_PATH:
{_pretty(evidence['category_path'])}

PATH_PRODUCT_COUNT:
{evidence['path_product_count']}

The following products are a deterministic sample from this Amazon path.

SAMPLED_PRODUCTS:
{_pretty(llm_samples)}

Determine whether this path should be KEEP, SPLIT, or REVIEW at the competition-market granularity defined in the system instructions.

Generate market rules that can later be applied deterministically to all product titles in this path.

Remember:

- identify the central purchased product or primary function;
- ignore brand/model/color/material/style differences;
- do not assume the Amazon category path is semantically clean;
- tolerate isolated taxonomy noise;
- do not force every title into a market;
- prefer stable generic market labels."""


def render_round2_system_prompt() -> str:
    return ROUND1_SYSTEM_PROMPT + "\n\nROUND 2 FINAL REVIEW\n\n" + ROUND2_APPENDIX


def render_round2_user_prompt(evidence: dict[str, Any]) -> str:
    counts = evidence["match_counts"]
    samples = evidence.get("samples", [])
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in samples:
        grouped.setdefault(str(row["provisional_group"]), []).append({
            "title": row.get("product_title") or row.get("title")})
    market_samples = {key: value for key, value in grouped.items() if key not in {"AMBIGUOUS", "UNMATCHED"}}
    return f"""Perform the final review for this Amazon path.

PATH_ID:
{evidence['path_id']}

SOURCE_PARTITION:
{evidence['source_partition']}

CATEGORY_PATH:
{_pretty(evidence['category_path'])}

PATH_PRODUCT_COUNT:
{evidence['path_product_count']}

ROUND 1 RESULT:

{_pretty({'decision': 'SPLIT', 'markets': evidence['round1_markets']})}

FULL-PATH RULE APPLICATION SUMMARY:

Total products:
{evidence['path_product_count']}

Market assignment counts:

{_pretty(counts.get('provisional_markets', []))}

AMBIGUOUS_COUNT:
{counts.get('ambiguous_count', 0)}

UNMATCHED_COUNT:
{counts.get('unmatched_count', 0)}

REPRESENTATIVE TITLES BY PROVISIONAL MARKET:

{_pretty(market_samples)}

AMBIGUOUS TITLE SAMPLES:

{_pretty(grouped.get('AMBIGUOUS', []))}

UNMATCHED TITLE SAMPLES:

{_pretty(grouped.get('UNMATCHED', []))}

Review the Round 1 definitions using the actual full-path matching results.

Return the final market definitions.

Remember:

- preserve broad purchase-object/function granularity;
- do not split by brand/model/material/style;
- do not create markets merely to absorb taxonomy noise;
- unmatched and ambiguous products are acceptable;
- this is the second and final round."""


def prompt_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


ARBITRATION_PROMPT_VERSION = "market_arbitration_v1"

ARBITRATION_SYSTEM_PROMPT = """You are an adjudicator for ambiguous product-market assignment.

You are given a product title and a list of candidate market names.
Your only task is to choose the single most appropriate candidate market for the product title.

Rules:

- You MUST select exactly one of the given candidate markets, or return null if none of them fits well.
- You MUST NOT create a new market name.
- You MUST NOT rename or modify a candidate market.
- You MUST NOT return any market outside the candidate list.
- Base your decision on the product identity in the title, not on brands, models, or generic spec words alone.

Return strictly valid JSON with exactly one key:
{"selected_market": "candidate name"}   or   {"selected_market": null}
"""


def render_arbitration_prompt(title: str, candidates: list[str]) -> tuple[str, str]:
    listing = "\n".join(f"- {name}" for name in candidates)
    user = f"""Product title:
{title}

Candidate markets:
{listing}

Select the most appropriate candidate market, or return null if none fits.
"""
    return ARBITRATION_SYSTEM_PROMPT, user


def render_prompt_pair(evidence: dict[str, Any], round_number: int) -> tuple[str, str]:
    if round_number == 1:
        return render_round1_system_prompt(), render_round1_user_prompt(evidence)
    if round_number == 2:
        return render_round2_system_prompt(), render_round2_user_prompt(evidence)
    raise ValueError("round_number must be 1 or 2")
