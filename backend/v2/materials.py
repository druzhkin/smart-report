from __future__ import annotations

import json
import re
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from backend.v2.models import MaterialKind, MaterialRecord
from backend.v2.repository import FileRunRepository


_TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml", ".yaml", ".yml"}


def _strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _docx_to_text(path: Path) -> str:
    document = Document(str(path))
    parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(parts).strip()


def _pdf_to_text(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        extracted = (page.extract_text() or "").strip()
        if extracted:
            chunks.append(extracted)
    return "\n".join(chunks).strip()


def _bytes_to_text(path: Path, media_type: str, raw: bytes) -> str:
    suffix = path.suffix.lower()
    if suffix in {".docx"}:
        return _docx_to_text(path)
    if suffix in {".pdf"}:
        return _pdf_to_text(path)

    decoded = raw.decode("utf-8", errors="replace")
    if suffix in {".json"}:
        try:
            parsed = json.loads(decoded)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return decoded.strip()
    if suffix in {".html", ".htm"} or "html" in (media_type or ""):
        return _strip_html(decoded)
    return decoded.strip()


def persist_binary_material(
    repo: FileRunRepository,
    run_id: str,
    *,
    title: str,
    filename: str,
    media_type: str,
    raw: bytes,
    kind: MaterialKind = MaterialKind.USER_UPLOAD,
) -> MaterialRecord:
    safe_name = Path(filename or "material.txt").name
    material = MaterialRecord(
        title=title or safe_name,
        filename=safe_name,
        media_type=media_type or "application/octet-stream",
        size_bytes=len(raw),
        kind=kind,
    )
    stored_filename = f"{material.material_id}{Path(safe_name).suffix.lower() or '.bin'}"
    stored_path = repo.write_material_file(run_id, stored_filename, raw)
    text = _bytes_to_text(stored_path, media_type, raw)
    text_filename = f"{material.material_id}.txt"
    repo.write_material_file(run_id, text_filename, text)
    material.stored_filename = stored_filename
    material.text_filename = text_filename
    material.text_length = len(text)
    material.excerpt = text[:280]
    return material


def persist_text_material(
    repo: FileRunRepository,
    run_id: str,
    *,
    title: str,
    content: str,
    kind: MaterialKind = MaterialKind.NOTE,
    filename: str | None = None,
    media_type: str = "text/plain",
) -> MaterialRecord:
    normalized = (content or "").strip()
    material = MaterialRecord(
        title=title or filename or "Material note",
        filename=filename or "material.txt",
        media_type=media_type,
        size_bytes=len(normalized.encode("utf-8")),
        kind=kind,
        text_length=len(normalized),
        excerpt=normalized[:280],
    )
    text_filename = f"{material.material_id}.txt"
    repo.write_material_file(run_id, text_filename, normalized)
    material.text_filename = text_filename
    if filename:
        stored_filename = f"{material.material_id}{Path(filename).suffix.lower() or '.txt'}"
        repo.write_material_file(run_id, stored_filename, normalized)
        material.stored_filename = stored_filename
    return material


def load_material_text(repo: FileRunRepository, run_id: str, material: MaterialRecord) -> str:
    if not material.text_filename:
        return ""
    path = repo.materials_dir(run_id) / material.text_filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
