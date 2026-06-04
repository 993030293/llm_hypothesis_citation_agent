from __future__ import annotations

import shutil
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QQ_UPLOAD_DIR = ROOT / "inputs" / "qq_uploads"


@dataclass(frozen=True)
class QQFileCandidate:
    source: str
    filename: str = ""
    file_id: str = ""
    size: int = 0


def candidates_from_segments(segments: list[dict[str, Any]]) -> list[QQFileCandidate]:
    candidates: list[QQFileCandidate] = []
    for seg in segments:
        if not isinstance(seg, dict) or seg.get("type") not in {"file", "image"}:
            continue
        data = seg.get("data", {}) or {}
        candidates.extend(candidates_from_file_data(data))
    return candidates


def candidates_from_notice(event: dict[str, Any]) -> list[QQFileCandidate]:
    file_data = event.get("file", {}) or event.get("data", {}) or {}
    if not isinstance(file_data, dict):
        return []
    return candidates_from_file_data(file_data)


def candidates_from_file_data(data: dict[str, Any]) -> list[QQFileCandidate]:
    filename = str(
        data.get("name")
        or data.get("filename")
        or data.get("file_name")
        or data.get("file")
        or ""
    )
    file_id = str(data.get("file_id") or data.get("id") or "")
    size = _int_or_zero(data.get("size"))

    candidates: list[QQFileCandidate] = []
    for key in ("path", "local_path", "url", "file", "file_path"):
        value = data.get(key)
        if value:
            candidates.append(QQFileCandidate(source=str(value), filename=filename, file_id=file_id, size=size))
    if not candidates and filename:
        candidates.append(QQFileCandidate(source=filename, filename=filename, file_id=file_id, size=size))
    return candidates


def file_segment_paths(segments: list[dict[str, Any]]) -> list[str]:
    return [candidate.source for candidate in candidates_from_segments(segments)]


def materialize_first_pdf(
    candidates: list[QQFileCandidate] | list[str],
    *,
    upload_dir: Path = QQ_UPLOAD_DIR,
) -> tuple[Path | None, str]:
    for candidate in candidates:
        if isinstance(candidate, str):
            item = QQFileCandidate(source=candidate, filename=Path(candidate).name)
        else:
            item = candidate
        if not looks_like_pdf(item):
            continue
        try:
            return materialize_pdf(item, upload_dir=upload_dir), ""
        except Exception as exc:
            return None, f"PDF file was detected but could not be saved: {exc}"
    return None, "No PDF file was found in the QQ message."


def materialize_pdf(candidate: QQFileCandidate, *, upload_dir: Path = QQ_UPLOAD_DIR) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    source = candidate.source.strip()
    filename = safe_pdf_filename(candidate.filename or Path(urllib.parse.urlparse(source).path).name or "qq_upload.pdf")
    target = unique_target(upload_dir / filename)

    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in {"http", "https"}:
        with urllib.request.urlopen(source, timeout=60) as response:
            data = response.read()
        if not data.startswith(b"%PDF"):
            # Some servers add wrappers or do not expose PDF magic in the first
            # bytes, so suffix is still accepted. The check only guards obvious mistakes.
            if not filename.lower().endswith(".pdf"):
                raise ValueError("downloaded content does not look like a PDF")
        target.write_bytes(data)
        return target

    if parsed.scheme == "file":
        local_path = Path(urllib.request.url2pathname(parsed.path))
    else:
        local_path = Path(source.strip('"')).expanduser()
    if not local_path.is_absolute():
        local_path = (ROOT / local_path).resolve()
    if not local_path.exists():
        raise FileNotFoundError(str(local_path))
    if local_path.suffix.lower() != ".pdf":
        raise ValueError(f"not a PDF file: {local_path}")
    if local_path.parent.resolve() == upload_dir.resolve():
        return local_path
    if local_path.resolve() == target.resolve():
        return local_path
    shutil.copy2(local_path, target)
    return target


def looks_like_pdf(candidate: QQFileCandidate) -> bool:
    values = [candidate.filename, candidate.source]
    return any(str(value).lower().split("?", 1)[0].endswith(".pdf") for value in values if value)


def safe_pdf_filename(name: str) -> str:
    raw = Path(str(name or "qq_upload.pdf")).name
    if not raw.lower().endswith(".pdf"):
        raw = f"{raw}.pdf"
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw)
    return cleaned or "qq_upload.pdf"


def unique_target(path: Path) -> Path:
    stem = path.stem
    suffix = path.suffix or ".pdf"
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    candidate = path.with_name(f"{timestamp}_{stem}{suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{timestamp}_{stem}_{counter}{suffix}")
        counter += 1
    return candidate


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0
