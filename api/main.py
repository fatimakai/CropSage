"""FastAPI boundary for CropSage scoring, recommendations, and chat.

The finalized scoring endpoint is intentionally a thin adapter around the
deterministic engine. It accepts the three versioned input contracts and
returns the bare RecommendationOutput expected by the Next.js server client.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel, ConfigDict, Field

from agent.cropsage_agent import CropSageAgent
from scoring.score_crops import load_json, score_crops, validate
from services.recommendation_service import (
    RecommendationServiceError,
    execute_recommendation,
    get_planting_guidance,
    recommend_crops,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCHEMA_PATH = ROOT / "data" / "evidence" / "evidence_bundle.schema.json"
FARM_PROFILE_SCHEMA_PATH = ROOT / "data" / "farm-profile" / "farm_profile.schema.json"
RECOMMENDATION_SCHEMA_PATH = ROOT / "data" / "scoring" / "recommendation.schema.json"

EVIDENCE_SCHEMA_VERSION = os.getenv("EVIDENCE_BUNDLE_SCHEMA_VERSION", "1.2.0")
FARM_PROFILE_SCHEMA_VERSION = os.getenv("FARM_PROFILE_SCHEMA_VERSION", "1.0.0")
RECOMMENDATION_SCHEMA_VERSION = os.getenv("RECOMMENDATION_SCHEMA_VERSION", "1.0.0")
SCORING_ENGINE_VERSION = os.getenv("SCORING_ENGINE_VERSION", "1.0.0")
CROP_CATALOG_VERSION = os.getenv("CROP_CATALOG_VERSION", "1.1.0")
MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", str(8 * 1024 * 1024)))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("cropsage.api")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScoreRequest(StrictModel):
    farm_profile: dict[str, Any]
    evidence_bundle: dict[str, Any]
    scoring_config: dict[str, Any]


class ExecuteRecommendationRequest(StrictModel):
    farm_profile: dict[str, Any]


class RecommendationRequest(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    planting_month: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")
    irrigation_availability: Literal["yes", "no", "unknown"]
    crop_id: str | None = None
    soil_test_values: dict[str, Any] | None = None
    irrigation_reliability: str | None = None
    irrigation_method: str | None = None
    location_label: str | None = None


class PlantingGuidanceRequest(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    crop_id: str = Field(min_length=1)
    location_label: str | None = None


class ChatRequest(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=8_000)


def _error(status_code: int, code: str, message: str, request_id: str | None = None) -> JSONResponse:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if request_id:
        payload["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=payload)


def _require_version(payload: dict[str, Any], field: str, expected: str, label: str) -> None:
    actual = payload.get(field)
    if actual != expected:
        raise ValueError(f"{label} requires {field} {expected}; received {actual!r}")


def _validate_scoring_config(config: dict[str, Any]) -> None:
    _require_version(config, "schema_version", "1.0.0", "Scoring configuration")
    _require_version(config, "scoring_version", SCORING_ENGINE_VERSION, "Scoring configuration")
    if config.get("status") != "frozen":
        raise ValueError("Scoring configuration status must be 'frozen'")
    weights = config.get("weights_percent")
    if not isinstance(weights, dict) or not weights:
        raise ValueError("Scoring configuration must contain weights_percent")
    if abs(sum(float(value) for value in weights.values()) - 100.0) > 1e-9:
        raise ValueError("Scoring configuration weights must sum to 100")


def _score(payload: ScoreRequest) -> dict[str, Any]:
    profile = payload.farm_profile
    evidence = payload.evidence_bundle
    config = payload.scoring_config

    _require_version(profile, "schema_version", FARM_PROFILE_SCHEMA_VERSION, "Farm profile")
    _require_version(evidence, "schema_version", EVIDENCE_SCHEMA_VERSION, "EvidenceBundle")
    validate(profile, load_json(FARM_PROFILE_SCHEMA_PATH), "Farm profile")
    validate(evidence, load_json(EVIDENCE_SCHEMA_PATH), "EvidenceBundle")
    evidence_catalog_version = evidence.get("catalog", {}).get("version")
    if evidence_catalog_version != CROP_CATALOG_VERSION:
        raise ValueError(
            f"EvidenceBundle requires crop catalog {CROP_CATALOG_VERSION}; "
            f"received {evidence_catalog_version!r}"
        )
    if evidence.get("validation", {}).get("all_passed") is not True:
        raise ValueError("EvidenceBundle validation.all_passed must be true before scoring")
    _validate_scoring_config(config)

    result = score_crops(evidence, profile, config)
    _require_version(result, "schema_version", RECOMMENDATION_SCHEMA_VERSION, "Recommendation output")
    validate(result, load_json(RECOMMENDATION_SCHEMA_PATH), "Recommendation output")
    if result.get("status") != "validated":
        raise ValueError("Recommendation output is not validated and cannot be displayed")
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = None
    app.state.agent_lock = asyncio.Lock()
    yield
    agent = app.state.agent
    if agent is not None:
        agent.close()


app = FastAPI(
    title="CropSage Backend API",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENABLE_API_DOCS", "false").lower() == "true" else None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def request_boundary(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                return _error(413, "request_too_large", "Request body is too large", request_id)
        except ValueError:
            return _error(400, "invalid_content_length", "Invalid Content-Length header", request_id)

    started = time.perf_counter()
    response: Response = await call_next(request)
    response.headers["x-request-id"] = request_id
    LOGGER.info(
        "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, _exc: RequestValidationError):
    return _error(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid_request",
        "The request does not match the required API contract",
        getattr(request.state, "request_id", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    LOGGER.error(
        "request_failed request_id=%s path=%s exception_type=%s",
        request_id,
        request.url.path,
        type(exc).__name__,
    )
    return _error(500, "internal_error", "The request could not be completed", request_id)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "backend-api",
        "api_version": app.version,
        "contracts": {
            "evidence_bundle": EVIDENCE_SCHEMA_VERSION,
            "farm_profile": FARM_PROFILE_SCHEMA_VERSION,
            "recommendation": RECOMMENDATION_SCHEMA_VERSION,
            "crop_catalog": CROP_CATALOG_VERSION,
            "scoring_engine": SCORING_ENGINE_VERSION,
        },
    }


@app.post("/v1/recommendations/score")
async def score_recommendations(payload: ScoreRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_score, payload)
    except (ValueError, JsonSchemaValidationError) as exc:
        LOGGER.info("score_contract_rejected exception_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=422,
            detail="The scoring inputs failed finalized contract validation",
        ) from None


@app.post("/v1/recommendations/execute")
async def execute_recommendation_run(payload: ExecuteRecommendationRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(execute_recommendation, payload.farm_profile)
    except (RecommendationServiceError, ValueError, JsonSchemaValidationError) as exc:
        LOGGER.info("recommendation_execution_rejected exception_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=422,
            detail="The farm profile could not be prepared for deterministic scoring",
        ) from None


@app.post("/v1/recommendations")
async def recommendations(payload: RecommendationRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(recommend_crops, **payload.model_dump())
    except RecommendationServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/v1/planting-guidance")
async def planting_guidance(payload: PlantingGuidanceRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(get_planting_guidance, **payload.model_dump())
    except RecommendationServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def _get_agent(app_instance: FastAPI) -> CropSageAgent:
    if app_instance.state.agent is None:
        app_instance.state.agent = CropSageAgent()
    return app_instance.state.agent


@app.post("/v1/chat")
async def chat(payload: ChatRequest, request: Request) -> dict[str, Any]:
    async with request.app.state.agent_lock:
        agent = _get_agent(request.app)
        return await asyncio.to_thread(agent.chat, payload.message, payload.session_id)


@app.delete("/v1/chat/{session_id}", status_code=204)
async def reset_chat(session_id: str, request: Request) -> Response:
    if not session_id or len(session_id) > 128:
        raise HTTPException(status_code=422, detail="Invalid session_id")
    async with request.app.state.agent_lock:
        agent = _get_agent(request.app)
        agent.reset(session_id)
    return Response(status_code=204)
