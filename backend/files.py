"""Uploaded file storage and a cheap shape inspection (rows, cols, header).

Inspection is deliberately light (no pandas) so mock mode stays dependency-free.
The real engine re-reads the file however it likes.
"""

from __future__ import annotations

import asyncio
import csv
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import settings

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".xlsx"}
CHUNK = 1024 * 1024


@dataclass
class FileInfo:
    file_id: str
    filename: str
    path: Path
    size_bytes: int
    rows: int = 0
    cols: int = 0
    columns: list[str] = field(default_factory=list)

    def public(self) -> dict:
        """Shape returned by POST /api/upload."""
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "rows": self.rows,
            "cols": self.cols,
            "size_bytes": self.size_bytes,
            "columns": self.columns,
        }


_files: dict[str, FileInfo] = {}


def get_file(file_id: str) -> FileInfo | None:
    return _files.get(file_id)


async def save_upload(upload: UploadFile) -> FileInfo:
    filename = Path(upload.filename or "upload.csv").name
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"only {', '.join(sorted(ALLOWED_EXTENSIONS))} files, please")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex[:12]
    path = settings.upload_dir / f"{file_id}{ext}"
    limit = settings.max_upload_mb * 1024 * 1024

    size = 0
    with path.open("wb") as out:
        while chunk := await upload.read(CHUNK):
            size += len(chunk)
            if size > limit:
                out.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, f"file is bigger than {settings.max_upload_mb} MB")
            out.write(chunk)

    info = FileInfo(file_id=file_id, filename=filename, path=path, size_bytes=size)
    try:
        await asyncio.to_thread(inspect, info)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    _files[file_id] = info
    return info


def inspect(info: FileInfo) -> None:
    """Fill rows / cols / columns in place."""
    ext = info.path.suffix.lower()
    if ext == ".xlsx":
        _inspect_xlsx(info)
    else:
        _inspect_delimited(info, "\t" if ext == ".tsv" else None)


def _inspect_delimited(info: FileInfo, delimiter: str | None) -> None:
    with info.path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        if delimiter is None:
            sample = fh.read(64 * 1024)
            fh.seek(0)
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = ","
        reader = csv.reader(fh, delimiter=delimiter)
        header = next(reader, None)
        if not header:
            raise HTTPException(422, "that file looks empty")
        info.columns = [c.strip() or f"column_{i + 1}" for i, c in enumerate(header)]
        info.cols = len(info.columns)
        info.rows = sum(1 for row in reader if row)


def _inspect_xlsx(info: FileInfo) -> None:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise HTTPException(415, "xlsx support needs openpyxl (pip install openpyxl)") from exc
    wb = load_workbook(info.path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            raise HTTPException(422, "that sheet looks empty")
        info.columns = [str(c).strip() if c is not None else f"column_{i + 1}" for i, c in enumerate(header)]
        info.cols = len(info.columns)
        info.rows = sum(1 for row in rows if any(v is not None for v in row))
    finally:
        wb.close()
