from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_VERIFIER_PARAMS: dict[str, Any] = {
    "title_mismatch_threshold": 0.55,
    "title_match_threshold": 0.86,
    "title_partial_threshold": 0.65,
    "author_min_match_score": 0.0,
    "version_title_author_threshold": 0.92,
    "version_preprint_title_threshold": 0.86,
    "version_year_delta_max": 2,
    "support_green_overlap_threshold": 0.32,
    "support_green_similarity_threshold": 0.42,
    "support_partial_overlap_threshold": 0.12,
    "support_partial_similarity_threshold": 0.2,
    "support_score_green_min": 0.42,
    "green_min_source_agreement": 2,
    "allow_input_pdf_fulltext_green": False,
    "cap_green_when_input_extraction_risky": True,
    "strong_claim_terms": [
        "fully solves",
        "solves",
        "eliminates",
        "guarantees",
        "proves",
        "always",
        "never",
        "complete solution",
    ],
}


def load_verifier_params(
    params_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = dict(DEFAULT_VERIFIER_PARAMS)
    if params_path:
        path = Path(params_path)
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError(f"Verifier params file must contain a JSON object: {path}")
            params.update(loaded)
    if overrides:
        params.update({key: value for key, value in overrides.items() if value is not None})
    return params


def verifier_params_from_env() -> dict[str, Any]:
    return load_verifier_params(os.environ.get("CITATION_VERIFIER_PARAMS"))
