"""FastAPI wrapper around orchestrator.

Endpoints (see CLAUDE_CODE_OVERNIGHT_TASK.md §4):
  POST /api/research                      -> {id}, launches background research
  GET  /api/research/{id}/stream          -> SSE progress events
  POST /api/research/{id}/deepen          -> {cell, focus}
  POST /api/research/{id}/add-domain      -> {name, layers?} OR {freetext}
  POST /api/research/{id}/connect         -> {block_a_cell, block_b_cell}
  POST /api/research/{id}/dismiss         -> {cell}
  GET  /api/research/{id}/export/{fmt}    -> docx | pptx | md (json served too)
  GET  /api/research/{id}                 -> full report JSON
  GET  /api/reports                       -> list of saved reports
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Make sibling modules importable when launched via `uvicorn api.main:app`
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bootstrap_logging() -> None:
    """Force INFO-level logging to stdout so Railway/Docker capture pipeline events."""
    root = logging.getLogger()
    if getattr(root, "_smart_report_bootstrapped", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    # Replace any existing handlers uvicorn may have installed on root.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Quiet down HTTP libs so access logs don't drown pipeline logs.
    for noisy in ("httpx", "httpcore", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._smart_report_bootstrapped = True  # type: ignore[attr-defined]


_bootstrap_logging()
log = logging.getLogger("api")

from export import save_all, to_markdown  # noqa: E402
from models import Report  # noqa: E402
from orchestrator import (  # noqa: E402
    add_domain,
    connect_domains,
    deepen_cell,
    load_report,
    run_research,
    save_report,
)

REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Smart Report API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- in-memory registry of live jobs ----------

class _Job:
    def __init__(self, report_id: str, goal: str, depth: str = "standard"):
        self.id = report_id
        self.goal = goal
        self.depth = depth
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.status: str = "pending"  # pending | running | done | error
        self.error: str | None = None
        self.task: asyncio.Task | None = None
        self.dismissed_cells: set[str] = set()
        self.events: list[dict[str, Any]] = []

    def emit(self, event: str, message: str, **extra: Any) -> None:
        payload = {"event": event, "message": message, "ts": time.time(), **extra}
        self.events.append(payload)
        if len(self.events) > 2000:
            self.events = self.events[-1500:]
        try:
            self.queue.put_nowait(payload)
        except Exception:
            pass


JOBS: dict[str, _Job] = {}


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60] or "report"


def _make_id(goal: str) -> str:
    return f"{datetime.now():%Y%m%dT%H%M%S}-{_slugify(goal)}"


def _report_path(report_id: str) -> Path:
    return REPORTS_DIR / f"{report_id}.json"


def _status_path(report_id: str) -> Path:
    return REPORTS_DIR / f"{report_id}.status.json"


STALE_RUNNING_SECONDS = 600  # running jobs silent >10min are assumed dead (container killed on redeploy)


def _write_status(
    report_id: str,
    status: str,
    goal: str = "",
    error: str | None = None,
    phase: str | None = None,
) -> None:
    """Merge-write sidecar: preserves started_at, bumps updated_at on every call."""
    now = time.time()
    existing = _read_status(report_id) or {}
    payload = {
        "id": report_id,
        "status": status,
        "goal": goal or existing.get("goal", ""),
        "error": error if error is not None else existing.get("error"),
        "phase": phase if phase is not None else existing.get("phase"),
        "started_at": existing.get("started_at") or now,
        "updated_at": now,
        "ts": now,
    }
    try:
        _status_path(report_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _read_status(report_id: str) -> dict[str, Any] | None:
    p = _status_path(report_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _sidecar_view(sidecar: dict[str, Any]) -> dict[str, Any]:
    """Apply stale-running detection, return API-shaped status block."""
    status = sidecar.get("status", "unknown")
    error = sidecar.get("error")
    if status == "running":
        updated = float(sidecar.get("updated_at") or sidecar.get("ts") or 0)
        if updated and (time.time() - updated) > STALE_RUNNING_SECONDS:
            status = "abandoned"
            error = error or (
                f"worker went silent for >{STALE_RUNNING_SECONDS}s (likely container redeploy killed the job)"
            )
    return {"status": status, "error": error, "phase": sidecar.get("phase")}


def _persist(report_id: str, report: Report) -> None:
    save_report(report, _report_path(report_id))
    try:
        from llm import meter_snapshot
        from config import settings as _s
        snap = meter_snapshot()
        snap["currency_label"] = _s.currency_label
        snap["report_id"] = report_id
        snap["goal"] = report.goal
        (REPORTS_DIR / f"{report_id}.cost.json").write_text(
            json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _load(report_id: str) -> Report:
    path = _report_path(report_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"report {report_id} not found")
    return load_report(path)


# ---------- request models ----------


class ResearchStartIn(BaseModel):
    goal: str = Field(..., min_length=3)
    depth: Literal["light", "standard", "deep", "exhaustive"] = "standard"


class DeepenIn(BaseModel):
    cell: str
    focus: str = ""


class AddDomainIn(BaseModel):
    name: str | None = None
    layers: list[str] | None = None
    freetext: str | None = None


class ConnectIn(BaseModel):
    block_a_cell: str
    block_b_cell: str


class DismissIn(BaseModel):
    cell: str


# ---------- background runners ----------


async def _run_job(job: _Job) -> None:
    loop = asyncio.get_running_loop()
    t0 = time.time()

    def progress(event: str, message: str) -> None:
        payload = {"event": event, "message": message, "ts": time.time()}
        # Polling endpoint reads job.events; keep it in sync with the SSE queue.
        job.events.append(payload)
        if len(job.events) > 2000:
            job.events = job.events[-1500:]
        try:
            loop.call_soon_threadsafe(job.queue.put_nowait, payload)
        except RuntimeError:
            job.queue.put_nowait(payload)
        # Heartbeat: bump sidecar updated_at + current phase on every progress tick.
        _write_status(job.id, "running", goal=job.goal, phase=event)
        # Mirror to stdout so Railway/Docker logs capture every pipeline step.
        log.info("[%s] [%s] %s", job.id[-12:], event, message[:400])

    job.status = "running"
    _write_status(job.id, "running", goal=job.goal)
    job.emit("status", "running")
    log.info("[%s] job START goal=%r depth=%s", job.id[-12:], job.goal[:120], job.depth)
    try:
        report = await run_research(job.goal, progress=progress, depth=job.depth)
        _persist(job.id, report)
        job.status = "done"
        _write_status(job.id, "done", goal=job.goal)
        job.emit("done", f"report saved: {job.id}", report_id=job.id)
        log.info(
            "[%s] job DONE blocks=%d conns=%d elapsed=%.1fs",
            job.id[-12:], len(report.blocks), len(report.connections), time.time() - t0,
        )
    except Exception as err:  # pragma: no cover
        job.status = "error"
        job.error = str(err)
        _write_status(job.id, "error", goal=job.goal, error=str(err))
        job.emit("error", str(err))
        log.exception("[%s] job FAILED after %.1fs: %s", job.id[-12:], time.time() - t0, err)
    finally:
        # sentinel to close SSE stream
        job.queue.put_nowait({"event": "__end__", "message": ""})


async def _run_mutation(job: _Job, coro_factory) -> None:
    loop = asyncio.get_running_loop()

    def progress(event: str, message: str) -> None:
        payload = {"event": event, "message": message, "ts": time.time()}
        job.events.append(payload)
        if len(job.events) > 2000:
            job.events = job.events[-1500:]
        try:
            loop.call_soon_threadsafe(job.queue.put_nowait, payload)
        except RuntimeError:
            job.queue.put_nowait(payload)

    job.status = "running"
    job.emit("status", "running")
    try:
        report = await coro_factory(progress)
        _persist(job.id, report)
        job.status = "done"
        job.emit("done", f"report updated: {job.id}", report_id=job.id)
    except Exception as err:
        job.status = "error"
        job.error = str(err)
        job.emit("error", str(err))
    finally:
        job.queue.put_nowait({"event": "__end__", "message": ""})


# ---------- endpoints ----------


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/research")
async def start_research(payload: ResearchStartIn) -> dict[str, str]:
    report_id = _make_id(payload.goal)
    job = _Job(report_id, payload.goal, depth=payload.depth)
    JOBS[report_id] = job
    _write_status(report_id, "pending", goal=payload.goal)
    job.task = asyncio.create_task(_run_job(job))
    return {"id": report_id, "status": "pending", "depth": payload.depth}


@app.get("/api/research/{report_id}/events")
async def list_events(report_id: str, since: int = 0) -> dict[str, Any]:
    """Polling alternative to /stream — Railway's HTTP/2 proxy kills long-lived SSE."""
    job = JOBS.get(report_id)
    if job is None:
        if _report_path(report_id).exists():
            return {"events": [], "cursor": since, "status": "done"}
        sidecar = _read_status(report_id)
        if sidecar is None:
            raise HTTPException(404, f"job {report_id} not found")
        view = _sidecar_view(sidecar)
        return {"events": [], "cursor": since, "status": view["status"]}
    new_events = job.events[since:]
    return {
        "events": new_events,
        "cursor": since + len(new_events),
        "status": job.status,
    }


@app.get("/api/research/{report_id}/stream")
async def stream(report_id: str, request: Request) -> StreamingResponse:
    job = JOBS.get(report_id)
    if job is None:
        # maybe already completed: allow a trivial stream
        if _report_path(report_id).exists():
            async def _done_gen():
                yield f"event: done\ndata: {json.dumps({'report_id': report_id})}\n\n"
            return StreamingResponse(_done_gen(), media_type="text/event-stream")
        raise HTTPException(404, f"job {report_id} not found")

    async def event_gen():
        # send an initial comment to open the stream
        yield ": connected\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(job.queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                # keepalive
                yield ": keepalive\n\n"
                continue
            if msg.get("event") == "__end__":
                yield f"event: close\ndata: {json.dumps({'status': job.status})}\n\n"
                break
            event_name = msg.get("event", "message")
            data = json.dumps(msg, ensure_ascii=False)
            yield f"event: {event_name}\ndata: {data}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/research/{report_id}")
async def get_report(report_id: str) -> dict[str, Any]:
    job = JOBS.get(report_id)
    path = _report_path(report_id)
    if not path.exists():
        if job is None:
            sidecar = _read_status(report_id)
            if sidecar is None:
                raise HTTPException(404, f"report {report_id} not found")
            view = _sidecar_view(sidecar)
            return {
                "id": report_id,
                "status": view["status"],
                "error": view["error"],
                "phase": view["phase"],
                "report": None,
                "dismissed": [],
            }
        return {
            "id": report_id,
            "status": job.status,
            "error": job.error,
            "report": None,
            "dismissed": sorted(job.dismissed_cells),
        }
    report = load_report(path)
    return {
        "id": report_id,
        "status": job.status if job else "done",
        "error": job.error if job else None,
        "report": report.model_dump(),
        "dismissed": sorted(job.dismissed_cells) if job else [],
    }


@app.post("/api/research/{report_id}/deepen")
async def api_deepen(report_id: str, payload: DeepenIn) -> dict[str, str]:
    report = _load(report_id)
    job = JOBS.setdefault(report_id, _Job(report_id, report.goal))

    async def factory(progress):
        return await deepen_cell(report, payload.cell, payload.focus or "", progress=progress)

    job.task = asyncio.create_task(_run_mutation(job, factory))
    return {"id": report_id, "status": "running", "op": "deepen"}


@app.post("/api/research/{report_id}/add-domain")
async def api_add_domain(report_id: str, payload: AddDomainIn) -> dict[str, str]:
    report = _load(report_id)
    job = JOBS.setdefault(report_id, _Job(report_id, report.goal))

    domain_name = payload.name or payload.freetext
    if not domain_name:
        raise HTTPException(400, "Either 'name' or 'freetext' required")

    async def factory(progress):
        return await add_domain(
            report, domain_name, layers_hint=payload.layers, progress=progress
        )

    job.task = asyncio.create_task(_run_mutation(job, factory))
    return {"id": report_id, "status": "running", "op": "add-domain"}


@app.post("/api/research/{report_id}/connect")
async def api_connect(report_id: str, payload: ConnectIn) -> dict[str, str]:
    report = _load(report_id)
    job = JOBS.setdefault(report_id, _Job(report_id, report.goal))

    # Cell format: "Domain / Layer"  -> we extract domains to feed connect_domains
    domain_a = payload.block_a_cell.split(" / ", 1)[0].strip()
    domain_b = payload.block_b_cell.split(" / ", 1)[0].strip()

    async def factory(progress):
        return await connect_domains(report, domain_a, domain_b, progress=progress)

    job.task = asyncio.create_task(_run_mutation(job, factory))
    return {
        "id": report_id,
        "status": "running",
        "op": "connect",
        "domains": [domain_a, domain_b],
    }


@app.post("/api/research/{report_id}/dismiss")
async def api_dismiss(report_id: str, payload: DismissIn) -> dict[str, Any]:
    # Soft-hide: persist a "dismissed" list alongside the report.
    if not _report_path(report_id).exists():
        raise HTTPException(404, f"report {report_id} not found")
    job = JOBS.setdefault(report_id, _Job(report_id, ""))
    job.dismissed_cells.add(payload.cell)
    # also persist into the JSON file (under a top-level 'dismissed' key)
    data = json.loads(_report_path(report_id).read_text(encoding="utf-8"))
    dismissed = set(data.get("_dismissed", []))
    dismissed.add(payload.cell)
    data["_dismissed"] = sorted(dismissed)
    _report_path(report_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"id": report_id, "dismissed": sorted(dismissed)}


# ---------- export ----------


@app.get("/api/research/{report_id}/export/md")
async def export_md(report_id: str) -> StreamingResponse:
    report = _load(report_id)
    md = to_markdown(report)
    return StreamingResponse(
        iter([md.encode("utf-8")]),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{report_id}.md"',
        },
    )


@app.get("/api/research/{report_id}/export/json")
async def export_json(report_id: str) -> FileResponse:
    path = _report_path(report_id)
    if not path.exists():
        raise HTTPException(404, f"report {report_id} not found")
    return FileResponse(
        path, media_type="application/json", filename=f"{report_id}.json"
    )


@app.get("/api/research/{report_id}/export/onepager")
async def export_onepager(report_id: str) -> FileResponse:
    report = _load(report_id)
    from export_onepager import export_onepager_html
    out = REPORTS_DIR / f"{report_id}.onepager.html"
    export_onepager_html(report, out)
    return FileResponse(out, media_type="text/html; charset=utf-8",
                        filename=f"{report_id}.onepager.html")


@app.get("/api/research/{report_id}/export/docx")
async def export_docx(report_id: str) -> FileResponse:
    report = _load(report_id)
    # Prefer a pre-baked McKinsey-grade docx if Core agent produced one,
    # otherwise fall back to the baseline python-docx export.
    nice = REPORTS_DIR / f"{report_id}.docx"
    try:
        from export_docx import export_mckinsey_docx
        export_mckinsey_docx(report, nice)
    except Exception:
        import traceback
        traceback.print_exc()
        paths = save_all(report, REPORTS_DIR, stem=report_id)
        nice = paths["docx"]
    if not nice.exists():
        raise HTTPException(
            status_code=404,
            detail="DOCX exporter unavailable — Core agent has not produced the file yet.",
        )
    return FileResponse(
        nice,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{report_id}.docx",
    )


@app.get("/api/research/{report_id}/export/pptx")
async def export_pptx(report_id: str) -> FileResponse:
    nice = REPORTS_DIR / f"{report_id}.pptx"
    if not nice.exists():
        try:
            from export_pptx import export as export_pptx_fn  # type: ignore
            report = _load(report_id)
            export_pptx_fn(report, nice)
        except Exception:
            return JSONResponse(
                status_code=404,
                content={
                    "detail": "PPTX экспорт пока не готов — модуль export_pptx.py "
                              "ещё не реализован Core-агентом.",
                },
            )
    return FileResponse(
        nice,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"{report_id}.pptx",
    )


def _gamma_cache_path(report_id: str, fmt: str) -> Path:
    return REPORTS_DIR / f"{report_id}.gamma.{fmt}.json"


@app.get("/api/research/{report_id}/export/gamma")
async def export_gamma(report_id: str, format: str = "pptx", force: bool = False) -> Any:
    try:
        from config import settings  # local import to avoid circular issues at module load

        report = _load(report_id)
        fmt = format.lower()
        if fmt not in ("pptx", "pdf"):
            raise HTTPException(400, "format must be 'pptx' or 'pdf'")

        cache_path = _gamma_cache_path(report_id, fmt)
        if cache_path.exists() and not force:
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if cached.get("gamma_url"):
                    # If we don't yet have the export_url, try to refresh it.
                    if not cached.get("export_url") and cached.get("generation_id"):
                        try:
                            from export_gamma import poll_gamma_generation
                            fresh = await poll_gamma_generation(cached["generation_id"])
                            if fresh.get("export_url"):
                                cached["export_url"] = fresh["export_url"]
                                cache_path.write_text(json.dumps(cached), encoding="utf-8")
                        except Exception:
                            pass
                    return JSONResponse(
                        {**cached, "status": "cached", "cached": True},
                        status_code=200,
                    )
            except Exception:
                pass

        if not settings.gamma_api_key:
            if fmt == "pptx":
                return await export_pptx(report_id)
            return JSONResponse(
                {"detail": "Gamma API key не настроен. PDF через Gamma недоступен — используйте .pptx экспорт."},
                status_code=501,
            )

        try:
            from export_gamma import export_via_gamma
            result = await export_via_gamma(
                report,
                export_as=fmt,
                theme_id=settings.gamma_theme_id or None,
            )
        except Exception as err:
            if fmt == "pptx":
                return await export_pptx(report_id)
            return JSONResponse({"detail": f"Gamma export failed: {err}"}, status_code=502)

        payload = {
            "gamma_url": result.get("gamma_url"),
            "generation_id": result.get("generation_id"),
            "export_url": result.get("export_url"),
        }
        try:
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

        return JSONResponse(
            {
                **payload,
                "status": "generating" if not result.get("export_url") else "completed",
            },
            status_code=202 if not result.get("export_url") else 200,
        )
    except HTTPException:
        raise
    except Exception as err:
        import traceback
        traceback.print_exc()
        return JSONResponse({"detail": f"Export error: {err}"}, status_code=500)


@app.get("/api/research/{report_id}/export/gamma/status/{generation_id}")
async def export_gamma_status(report_id: str, generation_id: str) -> Any:
    try:
        from export_gamma import poll_gamma_generation
        data = await poll_gamma_generation(generation_id)
        if data.get("export_url"):
            for fmt in ("pptx", "pdf"):
                cp = _gamma_cache_path(report_id, fmt)
                if cp.exists():
                    try:
                        cached = json.loads(cp.read_text(encoding="utf-8"))
                        if cached.get("generation_id") == generation_id:
                            cached["export_url"] = data["export_url"]
                            if data.get("gamma_url"):
                                cached["gamma_url"] = data["gamma_url"]
                            cp.write_text(json.dumps(cached), encoding="utf-8")
                    except Exception:
                        pass
        return JSONResponse(data)
    except Exception as err:
        return JSONResponse({"status": "pending", "detail": str(err)}, status_code=200)


# ---------- library ----------


@app.get("/api/research/{report_id}/cost")
async def get_report_cost(report_id: str) -> dict[str, Any]:
    path = REPORTS_DIR / f"{report_id}.cost.json"
    if not path.exists():
        raise HTTPException(404, f"cost for {report_id} not recorded")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/research/{report_id}/status")
async def get_status(report_id: str) -> dict[str, Any]:
    sp = _status_path(report_id)
    if not sp.exists():
        return {"status": "unknown"}
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "unknown"}


@app.get("/api/reports")
async def list_reports() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(REPORTS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or "goal" not in data or "blocks" not in data:
            continue
        if path.stem.startswith("_") or path.stem.endswith(".status"):
            continue
        rid = path.stem
        blocks = data.get("blocks", []) or []
        conns = data.get("connections", []) or []
        exec_summary = data.get("exec_summary") or {}
        top_findings = exec_summary.get("top_findings", []) if isinstance(exec_summary, dict) else []
        items.append({
            "id": rid,
            "goal": data.get("goal", ""),
            "created_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            "blocks_count": len(blocks),
            "connections_count": len(conns),
            "top_findings_preview": [
                tf.get("headline", "") for tf in top_findings[:3]
            ],
        })
    return items
