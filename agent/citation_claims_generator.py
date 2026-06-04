from __future__ import annotations

import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from agent.hypothesis_generator import HypothesisGenerator
from agent.literature_search import LiteratureSearcher
from agent.pdf_reader import PdfReaderTool
from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import clean_text, top_keywords, write_json, write_jsonl


DEFAULT_FALLBACK_PROVIDERS = ["crossref", "openalex"]


class CitationAuditClaimsGenerator:
    """Generate citation-audit claims with the local auditable toolchain.

    Official DeepScientist is the preferred upstream agent in the campaign
    path. This generator is a deterministic recovery path for cases where the
    official quest times out or does not write `citation_audit_claims.json`.
    It still uses the same self-implemented PDF reader, literature searcher,
    and hypothesis generator used by the local workflow, and records its own
    tool/evidence logs.
    """

    USER_AGENT = "llm-hypothesis-citation-agent/0.1 (course project)"

    def __init__(self, run_dir: Path, *, timeout_seconds: int = 20):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.logger = ToolCallLogger(self.run_dir)
        self.evidence = EvidenceStore(self.run_dir)

    def generate(
        self,
        *,
        case_id: str,
        pdf_path_or_url: str,
        providers: list[str] | None = None,
        max_pages: int = 3,
        max_hypotheses: int = 3,
        max_results_per_query: int = 3,
    ) -> dict[str, Any]:
        pdf_path = self.resolve_pdf(pdf_path_or_url)

        reader = PdfReaderTool(self.logger, self.evidence)
        paper_summary = reader.read(pdf_path, max_pages=max_pages)

        searcher = LiteratureSearcher(self.logger, self.evidence, timeout_seconds=self.timeout_seconds)
        generator = HypothesisGenerator(self.logger, self.evidence, searcher=searcher)
        keywords = paper_summary.get("keywords") or top_keywords(
            f"{paper_summary.get('title', '')} {paper_summary.get('abstract', '')}",
            6,
        )
        query_text = " ".join([paper_summary.get("title", ""), *keywords[:5]]).strip()
        queries = [
            {
                "query_id": "Q001",
                "query": query_text or paper_summary.get("title", "scientific citation verification"),
                "query_stage": "official_ds_fallback",
                "query_type": "deterministic_seed",
                "purpose": "Recover citation-audit claims when official DeepScientist did not write claims JSON.",
            }
        ]
        literature = searcher.search(
            queries,
            providers or DEFAULT_FALLBACK_PROVIDERS,
            max_results_per_query=max_results_per_query,
        )
        hypothesis_payload = generator.generate(
            paper_summary,
            max_hypotheses=max_hypotheses,
            inject_bad_citation=False,
            literature=literature,
        )
        hypothesis_payload["literature"] = literature
        hypothesis_payload["queries"] = queries

        claims_payload = self.to_citation_audit_payload(
            case_id=case_id,
            pdf_path_or_url=pdf_path_or_url,
            paper_summary=paper_summary,
            hypothesis_payload=hypothesis_payload,
        )
        claims_path = self.run_dir / "citation_audit_claims.json"
        write_json(claims_path, claims_payload)

        write_json(self.run_dir / "fallback_paper_summary.json", paper_summary)
        write_json(self.run_dir / "fallback_generated_claims.json", hypothesis_payload)
        write_jsonl(self.run_dir / "fallback_retrieved_literature.jsonl", hypothesis_payload.get("literature", []))
        (self.run_dir / "fallback_generated_hypothesis.md").write_text(
            hypothesis_payload.get("markdown", ""),
            encoding="utf-8",
        )

        return {
            "claims_path": str(claims_path),
            "claims_count": len(claims_payload.get("claims", [])),
            "hypotheses_count": len(claims_payload.get("hypotheses", [])),
            "pdf_path": str(pdf_path),
            "paper_title": paper_summary.get("title", ""),
            "providers": providers or DEFAULT_FALLBACK_PROVIDERS,
        }

    def resolve_pdf(self, pdf_path_or_url: str) -> Path:
        source = clean_text(pdf_path_or_url)
        if source.startswith(("http://", "https://")):
            return self.download_pdf(source)
        path = Path(source)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise FileNotFoundError(f"PDF path does not exist: {path}")
        return path.resolve()

    def download_pdf(self, url: str) -> Path:
        resolved_url = self.resolve_pdf_url(url)
        parsed = urllib.parse.urlparse(resolved_url)
        suffix = ".pdf" if not Path(parsed.path).suffix else Path(parsed.path).suffix
        filename = Path(parsed.path).name or "downloaded_paper.pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}{suffix if suffix.lower() == '.pdf' else '.pdf'}"
        output_path = self.run_dir / "downloaded_pdf" / filename
        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path

        call_id = self.logger.next_id()
        started = time.perf_counter()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            resolved_url,
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/pdf,*/*"},
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=self.timeout_seconds) as response:
                with output_path.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
            self.logger.log(
                tool_call_id=call_id,
                tool_name="fallback_claims.download_pdf",
                inputs={"url": resolved_url},
                status="success",
                output_summary=f"Downloaded PDF to {output_path}",
                started_at=started,
                outputs={"path": str(output_path), "bytes": output_path.stat().st_size},
            )
            self.evidence.record(
                source_type="pdf_url",
                source=resolved_url,
                content_snippet=f"Downloaded source PDF for fallback claim generation: {resolved_url}",
                category="input_pdf_download",
                tool_call_id=call_id,
                url=resolved_url,
                metadata={"local_path": str(output_path), "bytes": output_path.stat().st_size},
            )
            return output_path
        except Exception as exc:
            self.logger.log(
                tool_call_id=call_id,
                tool_name="fallback_claims.download_pdf",
                inputs={"url": resolved_url},
                status="error",
                output_summary="Fallback PDF download failed.",
                started_at=started,
                error=str(exc),
            )
            raise

    def resolve_pdf_url(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc.lower() == "arxiv.org" and parsed.path.startswith("/abs/"):
            arxiv_id = parsed.path.split("/abs/", 1)[1].strip("/")
            return f"https://arxiv.org/pdf/{arxiv_id}"
        return url

    def to_citation_audit_payload(
        self,
        *,
        case_id: str,
        pdf_path_or_url: str,
        paper_summary: dict[str, Any],
        hypothesis_payload: dict[str, Any],
    ) -> dict[str, Any]:
        claims = []
        for idx, claim in enumerate(hypothesis_payload.get("claims", []), start=1):
            cited = claim.get("cited_work") or {}
            claims.append(
                {
                    "claim_id": clean_text(claim.get("claim_id")) or f"C{idx:03d}",
                    "hypothesis_id": clean_text(claim.get("hypothesis_id")) or "H001",
                    "claim_text": clean_text(claim.get("claim_text")),
                    "claim_role": clean_text(claim.get("claim_role")) or "citation_backed_claim",
                    "cited_work": {
                        "title": clean_text(cited.get("title")),
                        "authors": cited.get("authors") if isinstance(cited.get("authors"), list) else [],
                        "year": cited.get("year", ""),
                        "doi": clean_text(cited.get("doi")),
                        "venue": clean_text(cited.get("venue")),
                        "url": clean_text(cited.get("url")),
                        "retrieval_source": clean_text(cited.get("retrieval_source"))
                        or clean_text(cited.get("source"))
                        or "local_fallback_generator",
                        "abstract": clean_text(cited.get("abstract")),
                        "snippet": clean_text(cited.get("snippet")),
                    },
                }
            )
        return {
            "case_id": case_id,
            "generation_source": "local_fallback_claims_generator",
            "paper": {
                "title": paper_summary.get("title", ""),
                "pdf_path_or_url": pdf_path_or_url,
                "source_pdf": paper_summary.get("source_pdf", ""),
                "abstract": paper_summary.get("abstract", ""),
                "keywords": paper_summary.get("keywords", []),
            },
            "hypotheses": hypothesis_payload.get("hypotheses", []),
            "claims": claims,
        }
