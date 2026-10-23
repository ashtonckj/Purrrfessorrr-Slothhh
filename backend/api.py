"""HTTP routes. This is the frontend contract (see API.md); keep it stable."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .cats import CATS
from .config import settings
from .engines import get_engine
from .exporters import build_notebook, build_zip
from .files import Selection, get_file, save_upload
from .jobs import Job, jobs
from .sample_data import sample_csv

router = APIRouter(prefix="/api")
engine = get_engine()


class ExcludeRule(BaseModel):
    column: int
    value: str = Field(max_length=1000)


class AnalyzeIn(BaseModel):
    file_id: str
    columns: list[int] | None = None      # None = all
    target: int | None = None
    exclude: list[ExcludeRule] = Field(default_factory=list, max_length=50)


class ChatIn(BaseModel):
    job_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)


def _job_or_404(job_id: str) -> Job:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job (the server may have restarted)")
    return job


def _safe_stem(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    return re.sub(r"[^A-Za-z0-9_-]+", "_", stem)[:60] or "analysis"


def _selection(body: AnalyzeIn, cols: int) -> Selection:
    def check(i: int) -> int:
        if not 0 <= i < cols:
            raise HTTPException(422, f"column {i} does not exist (the file has {cols})")
        return i

    columns = None if body.columns is None else sorted({check(i) for i in body.columns})
    if columns == []:
        raise HTTPException(422, "pick at least one column")
    if body.target is not None and check(body.target) not in (columns or [body.target]):
        raise HTTPException(422, "the target must be one of the chosen columns")
    return Selection(columns, body.target, [(check(r.column), r.value.strip()) for r in body.exclude])


@router.get("/config")
async def get_config() -> dict:
    """Small bits of server state the settings panel shows."""
    return {
        "engine": engine.name,
        "max_upload_mb": settings.max_upload_mb,
        "cats": CATS,
    }


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    info = await save_upload(file)
    return info.public()


@router.post("/analyze")
async def analyze(body: AnalyzeIn) -> dict:
    info = get_file(body.file_id)
    if info is None:
        raise HTTPException(404, "no such file (upload it again)")
    job = jobs.create(info, _selection(body, info.cols))

    async def runner() -> None:
        try:
            await engine.run(job)
        except Exception as exc:  # never leave a stream hanging
            await job.emit("error", cat=None, message=f"the whole office tripped: {exc}")
        if not job.finished:
            await job.emit("done", health_score=job.health_score)

    jobs.run_in_background(runner())
    return {"job_id": job.id}


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    job = _job_or_404(job_id)
    last_id = request.headers.get("last-event-id")
    start = int(last_id) + 1 if last_id and last_id.isdigit() else 0

    # Reconnect after everything was delivered: 204 tells EventSource to stop.
    if job.finished and start >= len(job.events):
        return Response(status_code=204)

    async def gen():
        yield "retry: 2000\n\n"
        async for event in job.stream(start):
            if await request.is_disconnected():
                break
            if event is None:
                yield ": keep-alive\n\n"
                continue
            yield f"id: {event.id}\nevent: {event.type}\ndata: {json.dumps(event.data)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/results/{job_id}/{cat}")
async def results(job_id: str, cat: str) -> dict:
    job = _job_or_404(job_id)
    if cat not in CATS:
        raise HTTPException(404, f"no cat called {cat}")
    return {"cat": cat, "ready": cat in job.results, "cards": job.results.get(cat, [])}


@router.get("/export/{job_id}/zip")
async def export_zip(job_id: str) -> Response:
    job = _job_or_404(job_id)
    name = _safe_stem(job.file.filename)
    return Response(build_zip(job), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}_slothhh.zip"'})


@router.get("/export/{job_id}/notebook")
async def export_notebook(job_id: str) -> Response:
    job = _job_or_404(job_id)
    name = _safe_stem(job.file.filename)
    return JSONResponse(build_notebook(job), media_type="application/x-ipynb+json",
                        headers={"Content-Disposition": f'attachment; filename="{name}_slothhh.ipynb"'})


@router.post("/chat")
async def chat(body: ChatIn) -> dict:
    job = jobs.get(body.job_id) if body.job_id else None
    reply = await engine.chat(job, body.message)
    return {"reply": reply.text, "from": reply.who, "choices": reply.choices}


@router.get("/sample.csv")
async def sample() -> Response:
    return Response(sample_csv(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="cafe_sales_sample.csv"'})
