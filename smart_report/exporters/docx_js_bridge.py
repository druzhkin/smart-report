"""
docx_js_bridge.py — Python subprocess bridge for the Node.js DOCX v2 renderer.

Public API:
    render_docx_js(final, output_path, chart_dir=None) -> Path

The function:
1. Serializes ``FinalReport`` to JSON (temp file).
2. Invokes ``node main.js <input.json> <output.docx> [--chart-dir <path>]``
   from the ``smart_report/exporters/docx_js/`` directory.
3. Returns the output path on success, or raises RuntimeError with node stderr.

Falls back gracefully:
- If ``node`` is not on PATH → raises NodeNotFoundError (a subclass of RuntimeError).
- If ``npm install`` was never run → node exits with an import error → RuntimeError.

Design notes:
- No LLM calls, no network calls — purely deterministic rendering.
- The JSON temp file is cleaned up after render (or on error).
- chart_dir is an optional Path to a directory with pre-rendered PNGs:
  ``chart_00.png``, ``chart_01.png``, … matching the order of ``data.charts``.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from smart_report.models import FinalReport

logger = logging.getLogger(__name__)

# Path to the Node.js renderer directory (sibling to this file)
_RENDERER_DIR = Path(__file__).parent / "docx_js"
_MAIN_JS = _RENDERER_DIR / "main.js"


class NodeNotFoundError(RuntimeError):
    """Raised when ``node`` executable is not found on PATH."""


class NodeRenderError(RuntimeError):
    """Raised when the Node.js renderer exits with a non-zero code."""


def _find_node() -> str:
    """Return the path to the ``node`` executable, or raise NodeNotFoundError."""
    node = shutil.which("node")
    if node is None:
        raise NodeNotFoundError(
            "Node.js not found on PATH. "
            "Install Node.js v22+ and make sure `node` is available, "
            "then run `npm install` in smart_report/exporters/docx_js/."
        )
    return node


def _check_node_modules() -> bool:
    """Return True if ``node_modules`` exists in the renderer directory."""
    return (_RENDERER_DIR / "node_modules").is_dir()


def render_docx_js(
    final: FinalReport,
    output_path: Path,
    chart_dir: Optional[Path] = None,
) -> Path:
    """
    Render a FinalReport to DOCX using the Node.js docx-js renderer.

    Parameters
    ----------
    final : FinalReport
        Pydantic v2 model instance to serialize.
    output_path : Path
        Destination path for the ``.docx`` file.
    chart_dir : Path or None
        Optional directory with pre-rendered chart PNGs.
        Files must be named ``chart_00.png``, ``chart_01.png``, …
        corresponding to ``final.charts`` index order.

    Returns
    -------
    Path
        Absolute path to the written ``.docx`` file.

    Raises
    ------
    NodeNotFoundError
        If ``node`` is not in PATH.
    NodeRenderError
        If the Node.js process exits with a non-zero code.
    FileNotFoundError
        If the renderer JS files are not present (missing ``npm install`` or corrupt install).
    """
    node_bin = _find_node()

    if not _MAIN_JS.exists():
        raise FileNotFoundError(
            f"Node.js renderer not found: {_MAIN_JS}\n"
            f"Expected directory: {_RENDERER_DIR}"
        )

    if not _check_node_modules():
        raise FileNotFoundError(
            f"node_modules not found in {_RENDERER_DIR}.\n"
            f"Run: cd {_RENDERER_DIR} && npm install"
        )

    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Serialize FinalReport to JSON
    report_dict = final.model_dump(mode="json")

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(report_dict, tmp, ensure_ascii=False, indent=None)
        tmp_json_path = Path(tmp.name)

    try:
        cmd = [node_bin, str(_MAIN_JS), str(tmp_json_path), str(output_path)]
        if chart_dir is not None:
            chart_dir = Path(chart_dir).resolve()
            cmd += ["--chart-dir", str(chart_dir)]

        logger.debug("Running Node.js renderer: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(_RENDERER_DIR),
            timeout=120,  # 2 minutes max for large documents
        )

        if result.stdout:
            logger.debug("Node stdout: %s", result.stdout.strip())
        if result.stderr:
            logger.warning("Node stderr: %s", result.stderr.strip())

        if result.returncode != 0:
            stderr_snippet = result.stderr[:2000] if result.stderr else "(no stderr)"
            raise NodeRenderError(
                f"Node.js renderer exited with code {result.returncode}.\n"
                f"Command: {' '.join(cmd)}\n"
                f"Stderr:\n{stderr_snippet}"
            )

        if not output_path.exists():
            raise NodeRenderError(
                f"Node.js renderer returned 0 but output file not found: {output_path}"
            )

        size_kb = output_path.stat().st_size // 1024
        logger.info("DOCX v2 rendered: %s (%d KB)", output_path, size_kb)
        return output_path

    finally:
        # Clean up temp JSON regardless of success or failure
        try:
            tmp_json_path.unlink(missing_ok=True)
        except OSError:
            pass


def is_node_available() -> bool:
    """Return True if Node.js is available and node_modules are installed."""
    try:
        _find_node()
        return _check_node_modules()
    except (NodeNotFoundError, OSError):
        return False
