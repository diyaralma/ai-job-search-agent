"""FastAPI uygulaması — web arayüzünün konuştuğu agent servisi."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import store
from .config import get_settings
from .cv.extract import UnsupportedCV
from .cv.parser import parse_cv
from .llm import describe_provider
from .pipeline import run_search
from .schemas import (
    ApplicationKitRequest,
    ApplicationKitResponse,
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
        "Agent servisi hazır (sağlayıcı=%s, model=%s, hazır=%s)",
        llm["provider"],
        llm["model"],
        llm["ready"],
    )
    if not llm["ready"]:
        logger.warning("LLM adımları çalışmayacak: %s", llm["detail"])
    yield


app = FastAPI(
    title="AI Job Search Agent",
    version="0.1.0",
    description="CV'den profil çıkarır, iş ilanlarını tarar ve adaya göre skorlar.",
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
    # llm.ready: seçili sağlayıcı çağrı yapmadan hazır mı (CLI var mı, anahtar
    # tanımlı mı…). Arayüz bunu görüp kullanıcıyı en baştan uyarıyor.
    return {
        "status": "ok",
        "llm": describe_provider(),
        "sources": [
            {"name": s.name, "enabled": s.enabled} for s in ALL_SOURCES
        ],
    }


@app.post("/api/cv", response_model=ProfileResponse)
async def upload_cv(file: UploadFile = File(...)) -> ProfileResponse:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Dosya 25 MB sınırını aşıyor.")

    try:
        profile = await parse_cv(file.filename or "cv.pdf", data)
    except UnsupportedCV as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("CV ayrıştırma başarısız")
        raise HTTPException(status_code=502, detail=f"CV analiz edilemedi: {exc}") from exc

    profile_id = f"prof_{uuid.uuid4().hex[:12]}"
    return await store.save_profile(profile_id, file.filename or "cv.pdf", profile)


@app.get("/api/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str) -> ProfileResponse:
    profile = await store.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profil bulunamadı.")
    return profile


@app.get("/api/profiles/{profile_id}/searches")
async def profile_searches(profile_id: str) -> list[dict]:
    return await store.list_searches(profile_id)


@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    stored = await store.get_profile(request.profile_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Profil bulunamadı. Önce CV yükleyin.")

    try:
        plan, stats, matches = await run_search(stored.profile, request.criteria)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Arama başarısız")
        raise HTTPException(status_code=502, detail=f"Arama tamamlanamadı: {exc}") from exc

    search_id = f"srch_{uuid.uuid4().hex[:12]}"
    await store.save_search(
        search_id, request.profile_id, request.criteria, plan, stats, matches
    )
    return SearchResponse(search_id=search_id, plan=plan, stats=stats, matches=matches)


@app.get("/api/searches/{search_id}", response_model=SearchResponse)
async def get_search(search_id: str) -> SearchResponse:
    result = await store.get_search(search_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Arama bulunamadı.")
    return result


# -- Başvuru kiti ----------------------------------------------------------
@app.post("/api/applications", response_model=ApplicationKitResponse)
async def create_application(request: ApplicationKitRequest) -> ApplicationKitResponse:
    """İlana özel CV + ön yazı üretir ve saklar."""
    stored = await store.get_profile(request.profile_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Profil bulunamadı.")

    job = await store.find_job(request.job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="İlan bulunamadı. Aramayı yeniden çalıştırıp tekrar deneyin.",
        )

    try:
        kit = await build_kit(stored.profile, job)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Başvuru kiti üretilemedi")
        raise HTTPException(status_code=502, detail=f"Başvuru kiti üretilemedi: {exc}") from exc

    application_id = f"app_{uuid.uuid4().hex[:12]}"
    return await store.save_application(application_id, request.profile_id, job, kit)


@app.get("/api/applications/{application_id}", response_model=ApplicationKitResponse)
async def get_application(application_id: str) -> ApplicationKitResponse:
    result = await store.get_application(application_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Başvuru kiti bulunamadı.")
    return result


@app.get("/api/applications/{application_id}/cv.{extension}")
async def download_cv(application_id: str, extension: str) -> Response:
    """Uyarlanmış CV'yi PDF ya da DOCX olarak indirir."""
    if extension not in ("pdf", "docx"):
        raise HTTPException(status_code=400, detail="Biçim 'pdf' veya 'docx' olmalı.")

    result = await store.get_application(application_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Başvuru kiti bulunamadı.")

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
