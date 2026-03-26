from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    status_code: int | None = None
    elapsed_ms: int | None = None


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _bool_env(name: str, default: bool = False) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


async def _check(
    client: httpx.AsyncClient,
    *,
    name: str,
    method: str,
    url: str,
    expected_status: set[int] | None = None,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> CheckResult:
    started = time.perf_counter()
    try:
        response = await client.request(method, url, headers=headers, json=json_body)
        elapsed = int((time.perf_counter() - started) * 1000)
        expected = expected_status or {200}
        ok = response.status_code in expected
        detail = response.text[:500] if not ok else "ok"
        return CheckResult(
            name=name,
            ok=ok,
            detail=detail,
            status_code=response.status_code,
            elapsed_ms=elapsed,
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return CheckResult(
            name=name,
            ok=False,
            detail=f"{type(exc).__name__}: {exc}",
            elapsed_ms=elapsed,
        )


async def _wait_report_completion(
    client: httpx.AsyncClient,
    api_base: str,
    session_id: str,
    timeout_sec: int,
) -> CheckResult:
    started = time.perf_counter()
    deadline = time.perf_counter() + timeout_sec
    last_status = "unknown"
    while time.perf_counter() < deadline:
        resp = await client.get(f"{api_base}/reports/{session_id}")
        if resp.status_code != 200:
            return CheckResult(
                name="backend.report_status",
                ok=False,
                detail=f"Unexpected status lookup code {resp.status_code}",
                status_code=resp.status_code,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        payload = resp.json()
        last_status = str(payload.get("status", "unknown"))
        if last_status in {"completed", "failed"}:
            return CheckResult(
                name="backend.report_status",
                ok=last_status == "completed",
                detail=f"final_status={last_status}",
                status_code=resp.status_code,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        await asyncio.sleep(3)

    return CheckResult(
        name="backend.report_status",
        ok=False,
        detail=f"timeout waiting completion (last_status={last_status})",
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )


async def main() -> int:
    api_base = _env("SMOKE_API_BASE")
    ragflow_base = _env("SMOKE_RAGFLOW_BASE_URL")
    ragflow_key = _env("SMOKE_RAGFLOW_API_KEY")
    ragflow_reports_dataset_id = _env("SMOKE_RAGFLOW_REPORTS_DATASET_ID")
    ragflow_facts_dataset_id = _env("SMOKE_RAGFLOW_FACTS_DATASET_ID")
    run_report = _bool_env("SMOKE_RUN_REPORT", default=False)
    report_timeout = int(_env("SMOKE_REPORT_TIMEOUT_SEC", "360") or "360")

    if not api_base:
        print("SMOKE_API_BASE is required, e.g. https://<your-domain>/api", file=sys.stderr)
        return 2

    results: list[CheckResult] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        results.append(
            await _check(
                client,
                name="backend.health",
                method="GET",
                url=f"{api_base}/health",
            )
        )
        results.append(
            await _check(
                client,
                name="backend.pricing",
                method="GET",
                url=f"{api_base}/reports/pricing",
            )
        )
        results.append(
            await _check(
                client,
                name="backend.reports_list",
                method="GET",
                url=f"{api_base}/reports",
            )
        )
        results.append(
            await _check(
                client,
                name="backend.library",
                method="GET",
                url=f"{api_base}/library",
            )
        )

        if run_report:
            started = time.perf_counter()
            try:
                create_response = await client.post(
                    f"{api_base}/reports",
                    json={
                        "request": "Smoke test report run. Validate pipeline availability only.",
                        "depth": "light",
                        "output_formats": ["html"],
                    },
                )
                create_elapsed = int((time.perf_counter() - started) * 1000)
                create_payload = create_response.json() if create_response.headers.get("content-type", "").startswith("application/json") else {}
                create_result = CheckResult(
                    name="backend.report_create",
                    ok=create_response.status_code == 200 and bool(create_payload.get("session_id")),
                    detail=json.dumps(create_payload, ensure_ascii=False)[:500],
                    status_code=create_response.status_code,
                    elapsed_ms=create_elapsed,
                )
            except Exception as exc:
                create_result = CheckResult(
                    name="backend.report_create",
                    ok=False,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            results.append(create_result)
            if create_result.ok:
                payload = json.loads(create_result.detail) if create_result.detail else {}
                session_id = payload.get("session_id")
                if session_id:
                    results.append(
                        await _wait_report_completion(
                            client,
                            api_base=api_base,
                            session_id=session_id,
                            timeout_sec=report_timeout,
                        )
                    )
                    results.append(
                        await _check(
                            client,
                            name="backend.report_download_html",
                            method="GET",
                            url=f"{api_base}/reports/{session_id}/download/html",
                            expected_status={200, 404},
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            name="backend.report_status",
                            ok=False,
                            detail="session_id missing in report create response",
                        )
                    )

        if ragflow_base:
            headers = {"Authorization": f"Bearer {ragflow_key}"} if ragflow_key else None
            datasets_check = await _check(
                client,
                name="ragflow.datasets",
                method="GET",
                url=f"{ragflow_base.rstrip('/')}/api/v1/datasets?page=1&page_size=200",
                headers=headers,
                expected_status={200} if ragflow_key else {200, 401, 403},
            )
            results.append(datasets_check)
            if datasets_check.ok and datasets_check.status_code == 200:
                try:
                    resp = await client.get(
                        f"{ragflow_base.rstrip('/')}/api/v1/datasets?page=1&page_size=200",
                        headers=headers,
                    )
                    payload = resp.json()
                    datasets: list[dict[str, Any]] = []
                    if isinstance(payload, dict):
                        data = payload.get("data")
                        if isinstance(data, list):
                            datasets = [d for d in data if isinstance(d, dict)]
                        elif isinstance(data, dict):
                            nested = data.get("docs") or data.get("items") or data.get("list")
                            if isinstance(nested, list):
                                datasets = [d for d in nested if isinstance(d, dict)]
                    dataset_ids = {str(d.get("id", "")) for d in datasets if d.get("id")}
                    if ragflow_reports_dataset_id:
                        results.append(
                            CheckResult(
                                name="ragflow.dataset_reports",
                                ok=ragflow_reports_dataset_id in dataset_ids,
                                detail=f"reports_dataset_found={ragflow_reports_dataset_id in dataset_ids}",
                            )
                        )
                    if ragflow_facts_dataset_id:
                        results.append(
                            CheckResult(
                                name="ragflow.dataset_facts",
                                ok=ragflow_facts_dataset_id in dataset_ids,
                                detail=f"facts_dataset_found={ragflow_facts_dataset_id in dataset_ids}",
                            )
                        )
                except Exception as exc:
                    results.append(
                        CheckResult(
                            name="ragflow.dataset_parse",
                            ok=False,
                            detail=f"{type(exc).__name__}: {exc}",
                        )
                    )

    failed = [r for r in results if not r.ok]
    summary = {
        "ok": len(failed) == 0,
        "checks_total": len(results),
        "checks_failed": len(failed),
        "results": [asdict(r) for r in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
