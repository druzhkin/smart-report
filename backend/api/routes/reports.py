from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.pricing import DEPTH_META, get_public_pricing
from backend.schemas.report_schema import ReportOutput
from backend.v2.intake import build_clarification_pack, build_request_spec, build_task_spec
from backend.v2.materials import persist_binary_material, persist_text_material
from backend.v2.models import ArtifactFormat, MaterialKind, RunEvent, RunStatus
from backend.v2.pipeline import build_draft_run, build_perplexity_handoff_prompts, build_research_plan, execute_report_run
from backend.v2.repository import FileRunRepository

router = APIRouter()
repo = FileRunRepository()

_live_queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}
_live_tasks: dict[str, asyncio.Task[None]] = {}


class CreateReportRequest(BaseModel):
    request: str = Field(..., min_length=1)
    depth: str = "standard"
    output_formats: list[str] = Field(default_factory=lambda: ["pdf", "html", "docx"])
    perplexity_handoff_enabled: bool = False


class ClarifyReportRequest(BaseModel):
    request: str = Field(..., min_length=1)
    depth: str = "standard"


class ScopeReportRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class MaterialTextRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    kind: str = "note"


def _coerce_output_formats(values: list[str]) -> list[ArtifactFormat]:
    formats: list[ArtifactFormat] = []
    for value in values:
        normalized = str(value or "").strip().lower()
        mapping = {
            "md": ArtifactFormat.MARKDOWN,
            "markdown": ArtifactFormat.MARKDOWN,
            "html": ArtifactFormat.HTML,
            "pdf": ArtifactFormat.PDF,
            "docx": ArtifactFormat.DOCX,
            "json": ArtifactFormat.JSON,
            "pptx": ArtifactFormat.PPTX,
        }
        candidate = mapping.get(normalized)
        if candidate and candidate not in formats:
            formats.append(candidate)
    if ArtifactFormat.MARKDOWN not in formats:
        formats.insert(0, ArtifactFormat.MARKDOWN)
    if ArtifactFormat.JSON not in formats:
        formats.append(ArtifactFormat.JSON)
    return formats


def _report_urls(run_id: str) -> dict[str, str]:
    path = repo.report_dir(run_id)
    urls: dict[str, str] = {}
    if (path / "report.md").exists():
        urls["md"] = f"/api/reports/{run_id}/download/md"
    if (path / "report.html").exists():
        urls["html"] = f"/api/reports/{run_id}/download/html"
    if (path / "report.pdf").exists():
        urls["pdf"] = f"/api/reports/{run_id}/download/pdf"
    if (path / "report.docx").exists():
        urls["docx"] = f"/api/reports/{run_id}/download/docx"
    if (path / "report.pptx").exists():
        urls["pptx"] = f"/api/reports/{run_id}/download/pptx"
    if (repo.run_dir(run_id) / "artifacts" / "report_output.json").exists():
        urls["json"] = f"/api/reports/{run_id}/download/json"
    return urls


def _load_report_output(run_id: str) -> ReportOutput | None:
    path = repo.run_dir(run_id) / "artifacts" / "report_output.json"
    if not path.exists():
        return None
    return ReportOutput.model_validate_json(path.read_text(encoding="utf-8"))


async def _publish(run_id: str, event: RunEvent) -> None:
    repo.append_event(run_id, event)
    logger.info(
        "run_id={} step={} status={} message={}",
        run_id,
        event.step,
        event.status,
        event.message,
    )
    queue = _live_queues.get(run_id)
    payload = {
        "event_id": event.event_id,
        "step": event.step,
        "status": event.status,
        "message": event.message,
        "timestamp": event.timestamp.isoformat(),
        "cost_usd": float(event.payload.get("cost_usd", 0.0)),
        "tokens_used": int(event.payload.get("tokens_used", 0)),
        **event.payload,
    }
    if queue is not None:
        await queue.put(payload)


async def _run_background(run_id: str) -> None:
    summary = repo.get_run(run_id)
    if summary is None or summary.task_spec is None:
        logger.warning("run_id={} background task started without a task spec", run_id)
        return
    logger.info("run_id={} background pipeline starting", run_id)
    summary.status = RunStatus.RUNNING
    repo.save_run(summary)
    await _publish(run_id, RunEvent(step="pipeline", status="started", message="Pipeline started"))
    try:
        summary = await execute_report_run(repo, summary, summary.task_spec, lambda event: _publish(run_id, event))
        summary.report_url_map = _report_urls(run_id)
        repo.save_run(summary)
        final_status = "done" if summary.status == RunStatus.COMPLETED else "error"
        await _publish(
            run_id,
            RunEvent(
                step="complete" if final_status == "done" else "pipeline",
                status=final_status,
                message="Report ready" if final_status == "done" else "Release gate blocked publication",
                payload={
                    "report_urls": summary.report_url_map,
                    "cost_usd": summary.cost_usd,
                    "tokens_used": summary.tokens_used,
                },
            ),
        )
        logger.info(
            "run_id={} background pipeline finished status={} release_status={}",
            run_id,
            summary.status.value,
            summary.audit_summary.release_status if summary.audit_summary else None,
        )
    except Exception as exc:
        logger.exception("run_id={} background pipeline crashed: {}", run_id, exc)
        summary = repo.get_run(run_id)
        if summary is not None:
            summary.status = RunStatus.FAILED
            repo.save_run(summary)
        await _publish(run_id, RunEvent(step="pipeline", status="error", message=str(exc)))
    finally:
        queue = _live_queues.get(run_id)
        if queue is not None:
            await queue.put(None)
        _live_tasks.pop(run_id, None)


def _ensure_run(run_id: str):
    summary = repo.get_run(run_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return summary


@router.post("/reports")
async def create_report(body: CreateReportRequest) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    summary = build_draft_run(
        run_id,
        body.request,
        depth=body.depth,
        output_formats=_coerce_output_formats(body.output_formats),
        allow_perplexity_handoff=body.perplexity_handoff_enabled,
    )
    summary.status = RunStatus.AWAITING_SCOPE
    repo.create_run(summary)
    logger.info(
        "run_id={} draft report created depth={} formats={}",
        run_id,
        body.depth,
        ",".join(body.output_formats),
    )
    return {
        "session_id": run_id,
        "estimated_time_minutes": int(DEPTH_META.get(body.depth, DEPTH_META["standard"])["estimated_time_minutes"]),
        "request_spec": summary.request_spec.model_dump(mode="json") if summary.request_spec else None,
        "status": summary.status.value,
    }


@router.post("/reports/clarify")
async def clarify_report(body: ClarifyReportRequest) -> dict[str, Any]:
    request_spec = build_request_spec(body.request, depth=body.depth)
    pack = build_clarification_pack("adhoc", request_spec)
    return pack.model_dump(mode="json")


@router.post("/reports/{run_id}/clarify")
async def clarify_report_for_run(run_id: str) -> dict[str, Any]:
    summary = _ensure_run(run_id)
    if summary.request_spec is None:
        raise HTTPException(status_code=400, detail="Request spec missing")
    pack = build_clarification_pack(run_id, summary.request_spec)
    return pack.model_dump(mode="json")


@router.post("/reports/{run_id}/scope")
async def scope_report(run_id: str, body: ScopeReportRequest) -> dict[str, Any]:
    summary = _ensure_run(run_id)
    if summary.request_spec is None:
        raise HTTPException(status_code=400, detail="Request spec missing")
    task_spec = build_task_spec(
        summary.request_spec,
        answers=body.answers,
        output_formats=[item.value for item in summary.requested_output_formats],
        allow_perplexity_handoff=summary.allow_perplexity_handoff,
        material_ids=[item.material_id for item in summary.materials],
    )
    summary.task_spec = task_spec
    if summary.allow_perplexity_handoff:
        summary.handoff_prompts = build_perplexity_handoff_prompts(task_spec, build_research_plan(task_spec))
        summary.status = RunStatus.AWAITING_HANDOFF
        repo.save_artifact(
            run_id,
            "handoff_prompts.json",
            [item.model_dump(mode="json") for item in summary.handoff_prompts],
        )
    else:
        summary.status = RunStatus.RUNNING
        _live_queues[run_id] = asyncio.Queue()
        _live_tasks[run_id] = asyncio.create_task(_run_background(run_id))
    repo.save_run(summary)
    logger.info(
        "run_id={} scope accepted answers={} must_cover_questions={}",
        run_id,
        len(body.answers),
        len(task_spec.must_cover_questions),
    )
    return {
        "session_id": run_id,
        "status": summary.status.value,
        "task_spec": task_spec.model_dump(mode="json"),
        "handoff_prompts": [item.model_dump(mode="json") for item in summary.handoff_prompts],
    }


@router.post("/reports/{run_id}/resume")
async def resume_report(run_id: str) -> dict[str, Any]:
    summary = _ensure_run(run_id)
    if summary.task_spec is None:
        raise HTTPException(status_code=400, detail="Task spec missing")
    if summary.status not in {RunStatus.AWAITING_HANDOFF, RunStatus.AWAITING_SCOPE}:
        raise HTTPException(status_code=400, detail="Run is not waiting for manual handoff")
    summary.status = RunStatus.RUNNING
    repo.save_run(summary)
    _live_queues[run_id] = asyncio.Queue()
    _live_tasks[run_id] = asyncio.create_task(_run_background(run_id))
    return {"session_id": run_id, "status": summary.status.value}


@router.get("/reports/{run_id}/materials")
async def get_report_materials(run_id: str) -> dict[str, Any]:
    summary = _ensure_run(run_id)
    return {
        "run_id": run_id,
        "materials": [item.model_dump(mode="json") for item in summary.materials],
    }


@router.post("/reports/{run_id}/materials/text")
async def add_report_text_material(run_id: str, body: MaterialTextRequest) -> dict[str, Any]:
    summary = _ensure_run(run_id)
    kind = MaterialKind.EXTERNAL_RESEARCH if body.kind == "external_research" else MaterialKind.NOTE
    material = persist_text_material(
        repo,
        run_id,
        title=body.title,
        content=body.content,
        kind=kind,
        filename=f"{body.title}.txt",
    )
    summary.materials.append(material)
    repo.save_artifact(run_id, "materials.json", [item.model_dump(mode="json") for item in summary.materials])
    repo.save_run(summary)
    return {"run_id": run_id, "material": material.model_dump(mode="json"), "materials": [item.model_dump(mode="json") for item in summary.materials]}


@router.post("/reports/{run_id}/materials/upload")
async def upload_report_material(
    run_id: str,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    kind: str = Form(default="user_upload"),
) -> dict[str, Any]:
    summary = _ensure_run(run_id)
    raw = await file.read()
    material_kind = MaterialKind.EXTERNAL_RESEARCH if kind == "external_research" else MaterialKind.USER_UPLOAD
    material = persist_binary_material(
        repo,
        run_id,
        title=title or file.filename or "Uploaded material",
        filename=file.filename or "material.bin",
        media_type=file.content_type or "application/octet-stream",
        raw=raw,
        kind=material_kind,
    )
    summary.materials.append(material)
    repo.save_artifact(run_id, "materials.json", [item.model_dump(mode="json") for item in summary.materials])
    repo.save_run(summary)
    return {"run_id": run_id, "material": material.model_dump(mode="json"), "materials": [item.model_dump(mode="json") for item in summary.materials]}


@router.get("/reports/pricing")
async def get_report_pricing() -> dict[str, Any]:
    return {"tiers": get_public_pricing(repo=repo)}


@router.get("/reports")
async def list_reports() -> list[dict[str, Any]]:
    items = []
    for summary in repo.list_runs():
        items.append(
            {
                "session_id": summary.run_id,
                "title": summary.title,
                "status": summary.status.value,
                "created_at": summary.created_at.isoformat(),
                "cost_usd": summary.cost_usd,
                "verdict": summary.audit_summary.release_status.upper() if summary.audit_summary else None,
                "output_formats": sorted(_report_urls(summary.run_id).keys()),
            }
        )
    return items


@router.get("/reports/{run_id}")
async def get_report(run_id: str) -> dict[str, Any]:
    summary = _ensure_run(run_id)
    report = _load_report_output(run_id)
    return {
        "session_id": run_id,
        "status": summary.status.value,
        "cost_usd": summary.cost_usd,
        "tokens_used": summary.tokens_used,
        "report_urls": _report_urls(run_id),
        "report": report.model_dump(mode="json") if report else None,
        "created_at": summary.created_at.isoformat(),
        "title": summary.title,
        "depth_profile": summary.depth_profile.model_dump(mode="json") if summary.depth_profile else None,
        "spend_breakdown": [item.model_dump(mode="json") for item in summary.spend_breakdown],
        "materials": [item.model_dump(mode="json") for item in summary.materials],
        "handoff_prompts": [item.model_dump(mode="json") for item in summary.handoff_prompts],
        "request_spec": summary.request_spec.model_dump(mode="json") if summary.request_spec else None,
        "task_spec": summary.task_spec.model_dump(mode="json") if summary.task_spec else None,
        "analysis_brief": summary.analysis_brief.model_dump(mode="json") if summary.analysis_brief else None,
        "coverage_report": summary.coverage_report.model_dump(mode="json") if summary.coverage_report else None,
        "audit_summary": summary.audit_summary.model_dump(mode="json") if summary.audit_summary else None,
    }


@router.get("/reports/{run_id}/stream")
async def stream_report(run_id: str) -> EventSourceResponse:
    _ensure_run(run_id)

    async def generator() -> AsyncGenerator[dict[str, str], None]:
        for event in repo.list_events(run_id):
            yield {"data": json.dumps(
                {
                    "event_id": event.event_id,
                    "step": event.step,
                    "status": event.status,
                    "message": event.message,
                    "timestamp": event.timestamp.isoformat(),
                    "cost_usd": float(event.payload.get("cost_usd", 0.0)),
                    "tokens_used": int(event.payload.get("tokens_used", 0)),
                    **event.payload,
                },
                ensure_ascii=False,
            )}

        queue = _live_queues.get(run_id)
        if queue is None:
            return
        while True:
            item = await queue.get()
            if item is None:
                break
            yield {"data": json.dumps(item, ensure_ascii=False)}

    return EventSourceResponse(generator())


@router.get("/reports/{run_id}/artifacts")
async def get_report_artifacts(run_id: str) -> dict[str, Any]:
    _ensure_run(run_id)
    artifacts = [path.name for path in sorted((repo.run_dir(run_id) / "artifacts").glob("*"))]
    package = [path.name for path in sorted(repo.list_report_files(run_id))]
    materials = [path.name for path in sorted(repo.list_material_files(run_id))]
    return {"run_id": run_id, "artifacts": artifacts, "package_files": package, "material_files": materials}


@router.get("/reports/{run_id}/evidence")
async def get_report_evidence(run_id: str) -> dict[str, Any]:
    _ensure_run(run_id)
    claim_table = repo.load_artifact(run_id, "claim_table.json") or []
    evidence = repo.load_artifact(run_id, "evidence_ledger.json") or []
    coverage = repo.load_artifact(run_id, "coverage_report.json") or {}
    return {"run_id": run_id, "claim_table": claim_table, "evidence_ledger": evidence, "coverage_report": coverage}


@router.get("/reports/{run_id}/sources")
async def get_report_sources(run_id: str) -> dict[str, Any]:
    _ensure_run(run_id)
    source_ledger = repo.load_artifact(run_id, "source_ledger.json") or []
    return {"run_id": run_id, "sources": source_ledger}


@router.get("/reports/{run_id}/download/{format}")
async def download_report(run_id: str, format: str) -> FileResponse:
    _ensure_run(run_id)
    if format == "json":
        path = repo.run_dir(run_id) / "artifacts" / "report_output.json"
    elif format == "md":
        path = repo.report_dir(run_id) / "report.md"
    elif format == "html":
        path = repo.report_dir(run_id) / "report.html"
    elif format == "pdf":
        path = repo.report_dir(run_id) / "report.pdf"
    elif format == "docx":
        path = repo.report_dir(run_id) / "report.docx"
    elif format == "pptx":
        path = repo.report_dir(run_id) / "report.pptx"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    if not path.exists():
        raise HTTPException(status_code=404, detail="File not ready or not found")
    return FileResponse(path)


@router.get("/evals")
async def get_evals() -> dict[str, Any]:
    latest = Path(settings.reports_evals_dir) / "latest.json"
    if not latest.exists():
        return {"status": "not_run"}
    return json.loads(latest.read_text(encoding="utf-8"))


@router.delete("/reports/{run_id}")
async def delete_report(run_id: str) -> dict[str, str]:
    summary = _ensure_run(run_id)
    run_dir = repo.run_dir(run_id)
    report_dir = repo.report_dir(run_id)
    for path in sorted(run_dir.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    if run_dir.exists():
        run_dir.rmdir()
    if report_dir.exists():
        for path in sorted(report_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        report_dir.rmdir()
    _live_queues.pop(run_id, None)
    task = _live_tasks.pop(run_id, None)
    if task is not None:
        task.cancel()
    return {"status": "ok", "deleted": summary.run_id}
