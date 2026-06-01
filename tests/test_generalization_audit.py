from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.generalization_audit import (
    build_domain_coverage,
    count_labels,
    ensure_case_pdf,
    resolve_pdf_url,
    run_subprocess,
    summarize_adapter_result,
    validate_manifest,
)


def test_manifest_validation_requires_core_fields() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        validate_manifest({"cases": [{"case_id": "demo", "field": "AI", "pdf_url": "https://example.test/x.pdf"}]})


def test_manifest_validation_rejects_duplicate_case_ids() -> None:
    manifest = {
        "cases": [
            {"case_id": "demo", "field": "AI", "pdf_url": "https://example.test/a.pdf", "pdf_path": "a.pdf"},
            {"case_id": "demo", "field": "AI", "pdf_url": "https://example.test/b.pdf", "pdf_path": "b.pdf"},
        ]
    }
    with pytest.raises(ValueError, match="Duplicate case_id"):
        validate_manifest(manifest)


def test_resolve_arxiv_abs_url_to_pdf() -> None:
    assert resolve_pdf_url("https://arxiv.org/abs/1812.05055") == "https://arxiv.org/pdf/1812.05055"


def test_downloader_skips_existing_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "existing.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfixture")
    case = {
        "case_id": "demo",
        "field": "AI",
        "pdf_url": "https://example.test/demo.pdf",
        "pdf_path": str(pdf),
    }
    row = ensure_case_pdf(case, force_download=False, skip_download=False, timeout_seconds=1)
    assert row["status"] == "skipped_existing"
    assert row["bytes"] == len(b"%PDF-1.4\nfixture")


def test_count_labels_defaults_missing_to_red() -> None:
    counts = count_labels([{"color_label": "Green"}, {"color_label": "Yellow"}, {}])
    assert counts == {"Green": 1, "Yellow": 1, "Red": 1}


def test_domain_coverage_aggregates_labels_and_completion() -> None:
    rows = [
        {
            "field": "AI",
            "workflow_status": "success",
            "artifact_complete": True,
            "green": 1,
            "yellow": 2,
            "red": 0,
        },
        {
            "field": "AI",
            "workflow_status": "failed",
            "artifact_complete": False,
            "green": 0,
            "yellow": 0,
            "red": 1,
        },
    ]
    coverage = build_domain_coverage(rows)
    assert coverage == [
        {
            "field": "AI",
            "case_count": 2,
            "completed_cases": 1,
            "green": 1,
            "yellow": 2,
            "red": 1,
            "artifact_complete": 1,
        }
    ]


def test_adapter_summary_handles_failed_adapter_without_outputs(tmp_path: Path) -> None:
    case = {"case_id": "demo", "field": "AI", "run_dir": str(tmp_path / "missing_run")}
    result = {"status": "failed", "returncode": 1, "stderr_tail": "boom"}
    summary = summarize_adapter_result(case, tmp_path / "missing_adapter", result)
    assert summary["adapter_status"] == "failed"
    assert summary["adapter_green"] == 0
    assert summary["adapter_yellow"] == 0
    assert summary["adapter_red"] == 0
    assert summary["stderr_tail"] == "boom"


def test_run_subprocess_captures_unicode_stdout() -> None:
    result = run_subprocess([sys.executable, "-c", "print('\\ufb01')"], timeout_seconds=5)
    assert result["status"] == "success"
    assert "\ufb01" in result["stdout_tail"]
