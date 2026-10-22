"""Uploaded file storage and a cheap shape inspection (rows, cols, header).

Inspection is deliberately light (no pandas) so mock mode stays dependency-free.
The real engine re-reads the file however it likes.
"""

from __future__ import annotations

import asyncio
import csv
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import settings

# Default is 128 KB per cell, which a single long text cell can exceed.
csv.field_size_limit(2**31 - 1)

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
    except Exception as exc:  # corrupt / unreadable file: explain instead of a bare 500
        path.unlink(missing_ok=True)
        raise HTTPException(422, f"could not read that file ({type(exc).__name__}: {exc})") from exc
    _files[file_id] = info
    return info


def inspect(info: FileInfo) -> None:
    """Fill rows / cols / columns in place."""
    rows = iter_rows(info)
    header = next(rows, None)
    if not header:
        raise HTTPException(422, "that file looks empty")
    info.columns = [str(c).strip() or f"column_{i + 1}" for i, c in enumerate(header)]
    info.cols = len(info.columns)
    info.rows = sum(1 for _ in rows)
    if info.rows == 0:
        raise HTTPException(422, "that file has a header but no data rows")


def iter_rows(info: FileInfo) -> Iterator[list]:
    """Yield the header, then the data rows, skipping blank lines.

    Shared by the upload check and the mock engine so they always agree.
    """
    if info.path.suffix.lower() == ".xlsx":
        yield from _iter_xlsx(info)
    else:
        yield from _iter_delimited(info)


def _encoding(path) -> str:
    with path.open("rb") as fh:
        head = fh.read(4)
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"            # Excel's "Unicode Text" export
    return "utf-8-sig"


def _iter_delimited(info: FileInfo) -> Iterator[list]:
    delimiter = "\t" if info.path.suffix.lower() == ".tsv" else None
    with info.path.open("r", encoding=_encoding(info.path), errors="replace", newline="") as fh:
        if delimiter is None:
            sample = fh.read(64 * 1024)
            fh.seek(0)
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = ","
        for row in csv.reader(fh, delimiter=delimiter):
            if any(cell.strip() for cell in row):
                yield row


def _iter_xlsx(info: FileInfo) -> Iterator[list]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise HTTPException(415, "xlsx support needs openpyxl (pip install openpyxl)") from exc
    wb = load_workbook(info.path, read_only=True, data_only=True)
    try:
        for row in wb.worksheets[0].iter_rows(values_only=True):
            if any(v is not None and str(v).strip() for v in row):
                yield ["" if v is None else v for v in row]
    finally:
        wb.close()
