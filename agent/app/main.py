"""FastAPI application — the agent service the web UI talks to."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import env_file, store
from .config import get_settings
from .cv.extract import UnsupportedCV
from .cv.parser import parse_cv
from .llm import describe_provider
from .pipeline import run_search
from .schemas import (
    ApplicationKitRequest,
    ApplicationKitResponse,
    JoobleSettings,
    JoobleSettingsRequest,
    ProfileResponse,
    SearchRequest,
    SearchResponse,
)
from .tailor.builder import build_kit
from .tailor.render import FontMissing, safe_filename, to_docx, to_pdf
from .sources.registry import ALL_SOURCES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init_db()
    llm = describe_provider()
    logger.info(
        "Agent service ready (provider=%s, model=%s, ready=%s)",
        llm["provider"],
        llm["model"],
        llm["ready"],
    )
    if not llm["ready"]:
        logger.warning("LLM steps will not work: %s", llm["detail"])
    yield


app = FastAPI(
    title="AI Job Search Agent",
    version="0.1.0",
    description="Extracts a profile from a CV, scans job postings and scores them for the candidate.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    # llm.ready: is the selected provider usable without making a call (is the
    # CLI present, is a key set…). The UI reads this and warns the user upfront.
    return {
        "status": "ok",
        "llm": describe_provider(),
        "sources": [
            {"name": s.name, "enabled": s.enabled} for s in ALL_SOURCES
        ],
    }


# -- Optional source credentials -------------------------------------------
# Jooble is the only source that carries Turkish job listings, and its keys are
# both free and REGIONAL — so every user needs their own, and the key alone is
# useless without the matching host. Making this settable from the UI saves
# people from editing agent/.env and restarting.
#
# Safe because the service binds to 127.0.0.1 and CORS is restricted to the
# local web UI. The key is stored in agent/.env and never read back out.
_ALLOWED_JOOBLE_HOSTS = {"https://jooble.org", "https://tr.jooble.org"}


@app.get("/api/settings/jooble", response_model=JoobleSettings)
async def jooble_settings() -> JoobleSettings:
    settings = get_settings()
    return JoobleSettings(configured=settings.jooble_enabled, host=settings.jooble_host)


@app.post("/api/settings/jooble", response_model=JoobleSettings)
async def set_jooble_settings(request: JoobleSettingsRequest) -> JoobleSettings:
    key = request.api_key.strip()
    host = request.host.strip().rstrip("/")

    if not key:
        raise HTTPException(status_code=400, detail="The API key cannot be empty.")
    # The host is where the key gets sent, so it is not free-form: restricting it
    # keeps a stray value from shipping the key somewhere else.
    if host not in _ALLOWED_JOOBLE_HOSTS:
        raise HTTPException(
            status_code=400,
            detail=f"Host must be one of: {', '.join(sorted(_ALLOWED_JOOBLE_HOSTS))}",
        )

    env_file.update({"JOOBLE_API_KEY": key, "JOOBLE_HOST": host})
    # Sources read the key through get_settings() on every call, so clearing the
    # cache is enough — no restart, no registry rebuild.
    get_settings.cache_clear()

    settings = get_settings()
    logger.info("Jooble source configured (host=%s)", settings.jooble_host)
    return JoobleSettings(configured=settings.jooble_enabled, host=settings.jooble_host)


@app.delete("/api/settings/jooble", response_model=JoobleSettings)
async def clear_jooble_settings() -> JoobleSettings:
    env_file.update({"JOOBLE_API_KEY": ""})
    get_settings.cache_clear()
    settings = get_settings()
    return JoobleSettings(configured=settings.jooble_enabled, host=settings.jooble_host)


@app.post("/api/cv", response_model=ProfileResponse)
async def upload_cv(file: UploadFile = File(...)) -> ProfileResponse:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 25 MB limit.")

    try:
        profile = await parse_cv(file.filename or "cv.pdf", data)
    except UnsupportedCV as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("CV parsing failed")
        raise HTTPException(status_code=502, detail=f"Could not analyze the CV: {exc}") from exc

    profile_id = f"prof_{uuid.uuid4().hex[:12]}"
    return await store.save_profile(profile_id, file.filename or "cv.pdf", profile)


@app.get("/api/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str) -> ProfileResponse:
    profile = await store.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return profile


@app.get("/api/profiles/{profile_id}/searches")
async def profile_searches(profile_id: str) -> list[dict]:
    return await store.list_searches(profile_id)


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    stored = await store.get_profile(request.profile_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Profile not found. Upload a CV first.")

    try:
        plan, stats, matches = await run_search(stored.profile, request.criteria)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Search failed")
        raise HTTPException(status_code=502, detail=f"Search could not be completed: {exc}") from exc

    search_id = f"srch_{uuid.uuid4().hex[:12]}"
    await store.save_search(
        search_id, request.profile_id, request.criteria, plan, stats, matches
    )
    return SearchResponse(search_id=search_id, plan=plan, stats=stats, matches=matches)


@app.get("/api/searches/{search_id}", response_model=SearchResponse)
async def get_search(search_id: str) -> SearchResponse:
    result = await store.get_search(search_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Search not found.")
    return result


# -- Application kit -------------------------------------------------------
@app.post("/api/applications", response_model=ApplicationKitResponse)
async def create_application(request: ApplicationKitRequest) -> ApplicationKitResponse:
    """Generates and stores a posting-specific CV + cover letter."""
    stored = await store.get_profile(request.profile_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Profile not found.")

    job = await store.find_job(request.job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Posting not found. Re-run the search and try again.",
        )

    try:
        kit = await build_kit(stored.profile, job)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not generate the application kit")
        raise HTTPException(status_code=502, detail=f"Could not generate the application kit: {exc}") from exc

    application_id = f"app_{uuid.uuid4().hex[:12]}"
    return await store.save_application(application_id, request.profile_id, job, kit)


@app.get("/api/applications/{application_id}", response_model=ApplicationKitResponse)
async def get_application(application_id: str) -> ApplicationKitResponse:
    result = await store.get_application(application_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Application kit not found.")
    return result


@app.get("/api/applications/{application_id}/cv.{extension}")
async def download_cv(application_id: str, extension: str) -> Response:
    """Downloads the tailored CV as PDF or DOCX."""
    if extension not in ("pdf", "docx"):
        raise HTTPException(status_code=400, detail="Format must be 'pdf' or 'docx'.")

    result = await store.get_application(application_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Application kit not found.")

    try:
        if extension == "pdf":
            payload = to_pdf(result.kit.cv, result.kit.language)
            media = "application/pdf"
        else:
            payload = to_docx(result.kit.cv, result.kit.language)
            media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    except FontMissing as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = safe_filename(result.kit.cv.full_name, result.job.company, extension)
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
