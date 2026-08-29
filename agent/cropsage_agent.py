"""Gemini-powered conversational agent for the CropSage recommendation service.

The LLM handles language understanding and explanations. It never calculates or
changes crop scores. Once the required farmer inputs are present, this controller
calls ``services.recommendation_service.recommend_crops`` and gives Gemini a
compact, read-only representation of the deterministic result.

Run an interactive terminal session from the repository root with::

    python -m agent.cropsage_agent
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError

from services.recommendation_service import (
    RecommendationServiceError,
    get_planting_guidance,
    recommend_crops,
    resolve_texas_location,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "crop-catalog" / "catalog.json"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_OPENROUTER_MODEL = "openrouter/free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_HISTORY_MESSAGES = 12


class AgentProviderUnavailable(RuntimeError):
    """All configured language-model providers are currently unavailable."""


class ExtractedTurn(BaseModel):
    """Structured interpretation of one farmer message."""

    intent: Literal["provide_information", "follow_up", "new_request", "reset"]
    request_type: Literal["crop_recommendation", "planting_guidance"] | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_label: str | None = None
    planting_month: str | None = Field(default=None, description="YYYY-MM only")
    irrigation_availability: Literal["yes", "no", "unknown"] | None = None
    irrigation_reliability: Literal[
        "reliable", "limited", "seasonal", "unreliable", "unknown"
    ] | None = None
    irrigation_method: Literal[
        "drip", "center_pivot", "sprinkler", "furrow", "flood", "subsurface", "other", "unknown"
    ] | None = None
    crop_id: str | None = None
    clear_crop_choice: bool = False
    soil_ph: float | None = None
    soil_tested_at: str | None = Field(default=None, description="YYYY-MM-DD only")
    soil_texture: str | None = None
    clear_soil_test_values: bool = False


class AgentGateway(Protocol):
    """Small interface that makes the conversation controller easy to test."""

    def extract(self, prompt: str) -> ExtractedTurn: ...

    def generate(self, prompt: str) -> str: ...


class GeminiGateway:
    """Google Gen AI SDK adapter used by the production agent."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing. Set it in the environment or install "
                "python-dotenv and place it in an uncommitted .env file."
            )
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Install the Gemini SDK with: python -m pip install google-genai") from exc
        self._types = types
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def extract(self, prompt: str) -> ExtractedTurn:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=ExtractedTurn,
                    automatic_function_calling=self._types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini input extraction request failed: {exc}") from exc
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, ExtractedTurn):
            return parsed
        if parsed is not None:
            return ExtractedTurn.model_validate(parsed)
        if not response.text:
            raise RuntimeError("Gemini returned no structured input extraction")
        return ExtractedTurn.model_validate_json(response.text)

    def generate(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    temperature=0.2,
                    automatic_function_calling=self._types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini explanation request failed: {exc}") from exc
        if not response.text:
            raise RuntimeError("Gemini returned no explanation")
        return _clean_model_text(response.text)

    def close(self) -> None:
        self._client.close()


class OpenRouterGateway:
    """Small dependency-free adapter for OpenRouter's chat-completions API."""

    def __init__(self, api_key: str, model: str = DEFAULT_OPENROUTER_MODEL) -> None:
        if not api_key:
            raise RuntimeError("OPEN_ROUTER_API_KEY is missing")
        self._api_key = api_key
        self._model = model

    def _complete(self, prompt: str, *, temperature: float) -> str:
        body = json.dumps(
            {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            }
        ).encode("utf-8")
        request = Request(
            OPENROUTER_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/FortyGuard-Tech/temperature-api-quickstart",
                "X-OpenRouter-Title": "CropSage",
            },
        )
        try:
            with urlopen(request, timeout=45) as response:  # noqa: S310 - fixed OpenRouter endpoint
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
        except (HTTPError, URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError("OpenRouter request unavailable") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter returned no text")
        return content.strip()

    def extract(self, prompt: str) -> ExtractedTurn:
        schema = json.dumps(ExtractedTurn.model_json_schema(), ensure_ascii=False)
        response = self._complete(
            f"{prompt}\n\nReturn one JSON object only, with no Markdown. It must validate against this schema:\n{schema}",
            temperature=0,
        )
        match = re.search(r"\{.*\}", response, flags=re.S)
        if not match:
            raise RuntimeError("OpenRouter returned invalid structured input")
        return ExtractedTurn.model_validate_json(match.group(0))

    def generate(self, prompt: str) -> str:
        return _clean_model_text(self._complete(prompt, temperature=0.2))


class FailoverGateway:
    """Try configured providers in order without exposing provider errors to farmers."""

    def __init__(self, gateways: list[AgentGateway]) -> None:
        if not gateways:
            raise RuntimeError("Configure GEMINI_API_KEY or OPEN_ROUTER_API_KEY in .env")
        self._gateways = gateways
        self.last_provider: str | None = None

    def _run(self, method: str, prompt: str) -> Any:
        for gateway in self._gateways:
            try:
                result = getattr(gateway, method)(prompt)
                self.last_provider = gateway.__class__.__name__.removesuffix("Gateway")
                return result
            except (RuntimeError, ValidationError, ValueError):
                continue
        raise AgentProviderUnavailable("No configured language-model provider completed the request")

    def extract(self, prompt: str) -> ExtractedTurn:
        return self._run("extract", prompt)

    def generate(self, prompt: str) -> str:
        return self._run("generate", prompt)

    def close(self) -> None:
        for gateway in self._gateways:
            close = getattr(gateway, "close", None)
            if callable(close):
                close()


@dataclass
class ConversationState:
    inputs: dict[str, Any] = field(default_factory=dict)
    recommendation: dict[str, Any] | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    language_provider: str = "not_used"


class CropSageAgent:
    """Stateful conversational controller around the deterministic service."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        gateway: AgentGateway | None = None,
        recommendation_function: Callable[..., dict[str, Any]] = recommend_crops,
        planting_guidance_function: Callable[..., dict[str, Any]] = get_planting_guidance,
        location_resolver: Callable[[str], dict[str, Any]] = resolve_texas_location,
    ) -> None:
        _load_dotenv_if_available()
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        if gateway is not None:
            self.gateway = gateway
        else:
            configured_gateways: list[AgentGateway] = []
            openrouter_key = os.getenv("OPEN_ROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
            if openrouter_key:
                configured_gateways.append(
                    OpenRouterGateway(
                        openrouter_key,
                        os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL),
                    )
                )
            gemini_key = api_key or os.getenv("GEMINI_API_KEY", "")
            if gemini_key:
                try:
                    configured_gateways.append(GeminiGateway(gemini_key, self.model))
                except RuntimeError:
                    # OpenRouter can still run the language layer when the optional
                    # Gemini SDK is not installed in a deployment environment.
                    pass
            self.gateway = FailoverGateway(configured_gateways)
        self.recommendation_function = recommendation_function
        self.planting_guidance_function = planting_guidance_function
        self.location_resolver = location_resolver
        self.crop_names = _load_crop_names()
        self.sessions: dict[str, ConversationState] = {}

    def reset(self, session_id: str = "default") -> None:
        self.sessions[session_id] = ConversationState()

    def chat(self, message: str, session_id: str = "default") -> dict[str, Any]:
        """Process one farmer message and return a UI-friendly response object."""
        if not isinstance(message, str) or not message.strip():
            return self._response(
                session_id,
                "error",
                "Please enter a message.",
                missing_fields=[],
            )
        state = self.sessions.setdefault(session_id, ConversationState())
        user_message = message.strip()
        try:
            extracted = self.gateway.extract(self._extraction_prompt(state, user_message))
            state.language_provider = getattr(
                self.gateway,
                "last_provider",
                self.gateway.__class__.__name__.removesuffix("Gateway"),
            ) or "configured_provider"
        except (RuntimeError, ValidationError, ValueError):
            extracted = self._local_extract(state, user_message)
            state.language_provider = "local_fallback"

        if extracted.intent == "reset":
            self.reset(session_id)
            return self._response(
                session_id,
                "needs_input",
                "The previous assessment has been cleared. Tell me what you want to grow and where your Texas farm is.",
                missing_fields=["location"],
                state=self.sessions[session_id],
            )

        if extracted.intent == "follow_up" and state.recommendation is not None:
            answer = self._answer_from_result(state, user_message)
            self._remember(state, user_message, answer)
            return self._response(session_id, "answer", answer, state=state)

        if extracted.intent == "new_request":
            state = ConversationState()
            self.sessions[session_id] = state
        self._merge_inputs(state.inputs, extracted)
        if state.inputs.get("unresolved_crop_name"):
            question = (
                f"I could not match {state.inputs['unresolved_crop_name']!r} to the 22 supported crops. "
                "Please choose a supported crop or ask me to rank all crops."
            )
            self._remember(state, user_message, question)
            return self._response(
                session_id,
                "needs_input",
                question,
                missing_fields=["crop_id"],
                state=state,
            )
        location_error = self._resolve_location_if_needed(state.inputs)
        if location_error:
            self._remember(state, user_message, location_error)
            return self._response(
                session_id,
                "needs_input",
                location_error,
                missing_fields=["location"],
                state=state,
            )
        missing = self._missing_fields(state.inputs)
        if missing:
            question = self._missing_input_question(missing)
            self._remember(state, user_message, question)
            return self._response(
                session_id,
                "needs_input",
                question,
                missing_fields=missing,
                state=state,
            )

        request_type = state.inputs.get("request_type", "crop_recommendation")
        try:
            if request_type == "planting_guidance":
                result = self.planting_guidance_function(**self._planting_guidance_arguments(state.inputs))
            else:
                result = self.recommendation_function(**self._service_arguments(state.inputs))
        except RecommendationServiceError as exc:
            message_text = f"I cannot run the recommendation yet: {exc}"
            self._remember(state, user_message, message_text)
            return self._response(session_id, "error", message_text, state=state)
        except Exception:  # The UI needs a safe boundary around provider/runtime errors.
            message_text = "The assessment could not be completed right now. Please try again."
            self._remember(state, user_message, message_text)
            return self._response(session_id, "error", message_text, state=state)

        state.recommendation = result
        try:
            explanation = self.gateway.generate(self._explanation_prompt(state, user_message))
            state.language_provider = getattr(
                self.gateway,
                "last_provider",
                self.gateway.__class__.__name__.removesuffix("Gateway"),
            ) or state.language_provider
        except (RuntimeError, ValueError):
            explanation = self._fallback_summary(result)
            state.language_provider = "local_fallback"
        self._remember(state, user_message, explanation)
        status = "planting_guidance" if request_type == "planting_guidance" else "recommendation"
        return self._response(session_id, status, explanation, state=state)

    def _extraction_prompt(self, state: ConversationState, message: str) -> str:
        crop_vocabulary = ", ".join(
            f"{crop_id} = {name}" for crop_id, name in self.crop_names.items()
        )
        return f"""You extract farmer inputs for CropSage. Return only the requested structured schema.

Rules:
- Never invent coordinates. Put any address, ZIP code, town, or place description in location_label so the application can geocode it.
- Remove conversational prefixes such as "near" or "outside" from location_label when possible.
- Set request_type=planting_guidance only when the farmer asks when or in which season/month to plant a named crop.
- Otherwise set request_type=crop_recommendation for a new assessment. Leave request_type null for ordinary follow-up details.
- If the current request is planting_guidance and the farmer then asks for a score or supplies a planting month/irrigation, set request_type=crop_recommendation.
- planting_month must be YYYY-MM. A month without a year remains null.
- Map crop names to exactly one crop_id from the vocabulary below.
- crop_id is optional. Use clear_crop_choice=true only when the farmer explicitly asks to rank all crops or removes a prior crop choice.
- Infer irrigation_availability=yes when the farmer explicitly says they have an irrigation system such as drip or center pivot.
- Soil pH is a laboratory override only when the user presents it as a measured/test result.
- follow_up means a question about an existing result without changing farm inputs.
- provide_information means initial details or changes to the current farm, crop, month, irrigation, or soil test.
- new_request means the user explicitly starts an assessment for a different farm.
- reset means the user explicitly asks to clear the conversation.
- Do not copy a value from Current collected inputs unless the user repeats or changes it; return null for unmentioned values.

Crop vocabulary:
{crop_vocabulary}

Existing recommendation: {state.recommendation is not None}
Current collected inputs:
{json.dumps(state.inputs, ensure_ascii=False, sort_keys=True)}

Farmer message:
{message}
"""

    def _local_extract(self, state: ConversationState, message: str) -> ExtractedTurn:
        """Conservative parser used when both hosted LLM providers are unavailable."""
        lowered = message.casefold().strip()
        if any(phrase in lowered for phrase in ("reset", "clear the conversation", "start over")):
            return ExtractedTurn(intent="reset")

        request_type: Literal["crop_recommendation", "planting_guidance"] | None = None
        planting_question = any(
            phrase in lowered
            for phrase in (
                "when should i plant",
                "when can i plant",
                "best time to plant",
                "best month to plant",
                "planting window",
            )
        )
        if planting_question:
            request_type = "planting_guidance"
        score_request = any(
            phrase in lowered
            for phrase in ("give me a score", "calculate the score", "run the score", "score this", "score it")
        )
        if not planting_question and (
            score_request or any(word in lowered for word in ("assess", "rank", "suitability", "recommend"))
        ):
            request_type = "crop_recommendation"

        latitude = longitude = None
        coordinate_match = re.search(
            r"(?<!\d)(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)(?!\d)",
            message,
        )
        if coordinate_match:
            latitude = float(coordinate_match.group(1))
            longitude = float(coordinate_match.group(2))

        location_label = None
        if latitude is None:
            location_match = re.search(
                r"\b(?:near|in|at|around|outside)\s+([A-Za-z0-9 .'-]+?(?:,\s*(?:Texas|TX))?)"
                r"(?=\s+(?:in|during|with|and|for)\b|[?.!,]|$)",
                message,
                flags=re.I,
            )
            if location_match:
                location_label = location_match.group(1).strip(" ,.")

        planting_month = None
        month_numbers = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        month_match = re.search(
            r"\b(" + "|".join(month_numbers) + r")\s+(20\d{2})\b",
            lowered,
        )
        if month_match:
            planting_month = f"{month_match.group(2)}-{month_numbers[month_match.group(1)]:02d}"

        irrigation_availability = None
        irrigation_reliability = None
        irrigation_method = None
        if re.search(r"\b(no|without)\s+(?:reliable\s+)?irrigation\b", lowered):
            irrigation_availability = "no"
        elif any(term in lowered for term in ("irrigation", "irrigated", "drip", "center-pivot", "center pivot")):
            irrigation_availability = "yes"
            if "drip" in lowered:
                irrigation_method = "drip"
            elif "center-pivot" in lowered or "center pivot" in lowered:
                irrigation_method = "center_pivot"
            if "reliable" in lowered:
                irrigation_reliability = "reliable"

        crop_mention = self._find_crop_mention(lowered)
        has_new_inputs = any(
            value is not None
            for value in (
                latitude,
                location_label,
                planting_month,
                irrigation_availability,
                crop_mention,
                request_type,
            )
        )
        if state.recommendation is not None and not has_new_inputs:
            intent: Literal["provide_information", "follow_up", "new_request", "reset"] = "follow_up"
        else:
            intent = "provide_information"
        if (
            state.inputs.get("request_type") == "planting_guidance"
            and (planting_month is not None or irrigation_availability is not None or score_request)
        ):
            request_type = "crop_recommendation"
        return ExtractedTurn(
            intent=intent,
            request_type=request_type,
            latitude=latitude,
            longitude=longitude,
            location_label=location_label,
            planting_month=planting_month,
            irrigation_availability=irrigation_availability,
            irrigation_reliability=irrigation_reliability,
            irrigation_method=irrigation_method,
            crop_id=crop_mention,
        )

    def _find_crop_mention(self, lowered_message: str) -> str | None:
        candidates = sorted(
            ((name.casefold(), crop_id) for crop_id, name in self.crop_names.items()),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        for name, crop_id in candidates:
            if name in lowered_message or crop_id.replace("_", " ") in lowered_message:
                return crop_id
        aliases = {
            "cotton": "upland_cotton",
            "spinach": "fresh_market_spinach",
            "cabbage": "fresh_market_cabbage",
            "rice": "long_grain_rice",
            "wheat": "hard_red_winter_wheat",
            "oats": "grain_oats",
            "peanut": "runner_peanut",
            "sunflower": "oilseed_sunflower",
            "watermelon": "seedless_watermelon",
            "onion": "dry_bulb_onion",
            "alfalfa": "alfalfa_hay",
            "bermudagrass": "bermudagrass_hay",
        }
        for term, crop_id in aliases.items():
            if re.search(rf"\b{re.escape(term)}\b", lowered_message):
                return crop_id
        return None

    def _merge_inputs(self, inputs: dict[str, Any], turn: ExtractedTurn) -> None:
        if turn.clear_crop_choice:
            inputs.pop("crop_id", None)
        if turn.clear_soil_test_values:
            for key in ("soil_ph", "soil_tested_at", "soil_texture"):
                inputs.pop(key, None)
        for key in (
            "request_type",
            "latitude",
            "longitude",
            "location_label",
            "planting_month",
            "irrigation_availability",
            "irrigation_reliability",
            "irrigation_method",
            "soil_ph",
            "soil_tested_at",
            "soil_texture",
        ):
            value = getattr(turn, key)
            if value is not None:
                inputs[key] = value
        if turn.crop_id is not None:
            canonical_crop_id = self._canonical_crop_id(turn.crop_id)
            if canonical_crop_id is not None:
                inputs["crop_id"] = canonical_crop_id
                inputs.pop("unresolved_crop_name", None)
            else:
                inputs["unresolved_crop_name"] = turn.crop_id

    def _canonical_crop_id(self, value: str) -> str | None:
        normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
        if normalized in self.crop_names:
            return normalized
        by_name = {
            re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_"): crop_id
            for crop_id, name in self.crop_names.items()
        }
        if normalized in by_name:
            return by_name[normalized]
        aliases = {
            "cotton": "upland_cotton",
            "spinach": "fresh_market_spinach",
            "cabbage": "fresh_market_cabbage",
            "rice": "long_grain_rice",
            "wheat": "hard_red_winter_wheat",
            "oats": "grain_oats",
            "peanut": "runner_peanut",
            "sunflower": "oilseed_sunflower",
            "watermelon": "seedless_watermelon",
            "onion": "dry_bulb_onion",
            "alfalfa": "alfalfa_hay",
            "bermudagrass": "bermudagrass_hay",
        }
        return aliases.get(normalized)

    @staticmethod
    def _missing_fields(inputs: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        if inputs.get("latitude") is None or inputs.get("longitude") is None:
            missing.append("location")
        if inputs.get("request_type", "crop_recommendation") == "planting_guidance":
            if inputs.get("crop_id") is None:
                missing.append("crop_id")
        else:
            for key in ("planting_month", "irrigation_availability"):
                if inputs.get(key) is None:
                    missing.append(key)
        if inputs.get("soil_ph") is not None and inputs.get("soil_tested_at") is None:
            missing.append("soil_tested_at")
        return missing

    @staticmethod
    def _missing_input_question(missing: list[str]) -> str:
        requests: list[str] = []
        if "location" in missing:
            requests.append("the farm's Texas address, ZIP code, nearby town, or coordinates")
        if "crop_id" in missing:
            requests.append("the crop you want planting dates for")
        if "planting_month" in missing:
            requests.append(
                "the intended planting month and year, or say 'tell me when to plant' for regional timing guidance"
            )
        if "irrigation_availability" in missing:
            requests.append("whether irrigation is available (yes, no, or unknown)")
        if "soil_tested_at" in missing:
            requests.append("the laboratory pH test date (YYYY-MM-DD)")
        if len(requests) == 1:
            return f"Please provide {requests[0]}."
        return "Please provide " + ", ".join(requests[:-1]) + f", and {requests[-1]}."

    def _resolve_location_if_needed(self, inputs: dict[str, Any]) -> str | None:
        if inputs.get("latitude") is not None and inputs.get("longitude") is not None:
            return None
        label = inputs.get("location_label")
        if not label:
            return None
        try:
            resolved = self.location_resolver(label)
        except RecommendationServiceError as exc:
            return str(exc)
        inputs["latitude"] = resolved["latitude"]
        inputs["longitude"] = resolved["longitude"]
        inputs["resolved_location_label"] = resolved["display_name"]
        inputs["geocoding_provider"] = resolved["provider"]
        return None

    @staticmethod
    def _service_arguments(inputs: dict[str, Any]) -> dict[str, Any]:
        soil_test: dict[str, Any] = {}
        if inputs.get("soil_ph") is not None:
            soil_test["ph"] = inputs["soil_ph"]
            soil_test["tested_at"] = inputs["soil_tested_at"]
        if inputs.get("soil_texture") is not None:
            soil_test["texture"] = inputs["soil_texture"]
        return {
            "latitude": inputs["latitude"],
            "longitude": inputs["longitude"],
            "planting_month": inputs["planting_month"],
            "irrigation_availability": inputs["irrigation_availability"],
            "irrigation_reliability": inputs.get("irrigation_reliability"),
            "irrigation_method": inputs.get("irrigation_method"),
            "crop_id": inputs.get("crop_id"),
            "soil_test_values": soil_test or None,
            "location_label": inputs.get("location_label"),
        }

    @staticmethod
    def _planting_guidance_arguments(inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "latitude": inputs["latitude"],
            "longitude": inputs["longitude"],
            "crop_id": inputs["crop_id"],
            "location_label": inputs.get("location_label"),
        }

    def _answer_from_result(self, state: ConversationState, question: str) -> str:
        try:
            return self.gateway.generate(self._follow_up_prompt(state, question))
        except (RuntimeError, ValueError):
            return self._deterministic_follow_up(state.recommendation or {}, question)

    def _explanation_prompt(self, state: ConversationState, farmer_message: str) -> str:
        return self._grounding_prompt(
            state,
            f"Explain the newly generated recommendation in plain language. The triggering farmer message was: {farmer_message}",
        )

    def _follow_up_prompt(self, state: ConversationState, question: str) -> str:
        return self._grounding_prompt(state, f"Answer this follow-up question: {question}")

    def _grounding_prompt(self, state: ConversationState, task: str) -> str:
        context = self._compact_recommendation(state.recommendation or {})
        return f"""You are CropSage's explanation assistant for Texas farmers.

Non-negotiable rules:
- Use only the deterministic result JSON below. Do not invent measurements, agronomic facts, scores, ranks, causes, or API evidence.
- Never calculate, adjust, rerank, or override a suitability or confidence score.
- Call confidence "evidence strength" in farmer-facing text. Explain it once when relevant; do not append it to every crop.
- Describe low confidence as limited evidence, not as a bad suitability result.
- Mention important hard gates and warnings. Mention regional reference distance only if it is over 50 km or the farmer asks about data sources.
- Give a short suggestion to confirm consequential decisions locally only when the farmer asks for action detail; do not repeat a legal-style disclaimer.
- Do not offer to answer topics that are absent from the result JSON.
- For planting_guidance, explicitly say that no suitability score is calculated until the farmer provides a specific planting month/year and irrigation availability.
- Be concise, practical, and use plain language.

Task:
{task}

Deterministic result JSON:
{json.dumps(context, ensure_ascii=False, allow_nan=False)}
"""

    @staticmethod
    def _compact_recommendation(service_result: dict[str, Any]) -> dict[str, Any]:
        if service_result.get("result_type") == "planting_guidance":
            return {
                "service_version": service_result.get("service_version"),
                "result_type": "planting_guidance",
                "farmer_request": service_result.get("request"),
                "location_resolution": service_result.get("location_resolution"),
                "guidance": service_result.get("guidance"),
            }
        recommendation = service_result.get("recommendation", {})
        compact_rankings = []
        for crop in recommendation.get("rankings", []):
            compact_rankings.append(
                {
                    "overall_rank": crop["overall_rank"],
                    "eligible_rank": crop["eligible_rank"],
                    "crop_id": crop["crop_id"],
                    "crop_name": crop["crop_name"],
                    "regionally_eligible": crop["regionally_eligible"],
                    "suitability_score": crop["suitability_score"],
                    "recommendation": crop["recommendation"],
                    "confidence_score": crop["confidence_score"],
                    "confidence_band": crop["confidence_band"],
                    "applied_gates": crop["applied_gates"],
                    "factor_scores": {
                        factor["factor_id"]: factor["score"]
                        for factor in crop["factors"]
                        if factor["available"]
                    },
                    "key_strengths": crop["key_strengths"],
                    "key_risks": crop["key_risks"],
                    "warnings": crop["warnings"],
                }
            )
        return {
            "service_version": service_result.get("service_version"),
            "farmer_request": service_result.get("request"),
            "location_resolution": service_result.get("location_resolution"),
            "scoring_version": recommendation.get("scoring_version"),
            "evaluation_mode": recommendation.get("evaluation_mode"),
            "requested_crop_id": recommendation.get("requested_crop_id"),
            "rankings": compact_rankings,
            "engine_limitations": recommendation.get("limitations"),
            "confidence_context": service_result.get("confidence_context"),
        }

    @staticmethod
    def _fallback_summary(service_result: dict[str, Any]) -> str:
        if service_result.get("result_type") == "planting_guidance":
            guidance = service_result["guidance"]
            windows = guidance.get("planting_windows", [])
            if not guidance.get("regionally_eligible"):
                return f"{guidance['crop_name']} is not supported in this CropSage region."
            if not windows:
                return f"CropSage does not yet have a planting window for {guidance['crop_name']} in this region."
            return (
                f"For {guidance['crop_name']} in this region, the catalog planting window is "
                f"{', '.join(windows)}. {guidance['regional_basis']} No suitability score is calculated "
                "for timing guidance alone. For a score, tell me the planting month and year you are considering "
                "and whether irrigation is available."
            )
        recommendation = service_result["recommendation"]
        top = recommendation["rankings"][:3]
        summary = "; ".join(
            f"{crop['crop_name']} {crop['suitability_score']}/100 ({crop['recommendation'].replace('_', ' ')})"
            for crop in top
        )
        return f"The top results are: {summary}. Open the crop details to review evidence strength and risks."

    @staticmethod
    def _deterministic_follow_up(service_result: dict[str, Any], question: str) -> str:
        lowered = question.casefold()
        if service_result.get("result_type") == "planting_guidance":
            guidance = service_result["guidance"]
            if "score" in lowered or "why" in lowered:
                return (
                    "This result has no suitability score because it answers regional planting timing only. "
                    "The scoring engine also needs the planting month and year you are considering and whether "
                    "irrigation is available. Provide those details and I can run the full score."
                )
            return CropSageAgent._fallback_summary(service_result)
        recommendation = service_result.get("recommendation", {})
        if "confidence" in lowered or "evidence" in lowered:
            context = service_result.get("confidence_context", {})
            return context.get(
                "explanation",
                "Evidence strength reflects the completeness and reliability of the available data, not crop suitability.",
            )
        requested = recommendation.get("requested_crop_result")
        featured = requested or (recommendation.get("rankings") or [None])[0]
        if featured and ("score" in lowered or "suitable" in lowered or "recommend" in lowered):
            return (
                f"{featured['crop_name']} has a suitability score of {featured['suitability_score']}/100 "
                f"and is classified as {featured['recommendation'].replace('_', ' ')}. "
                f"Its evidence strength is {featured['confidence_score']}/100."
            )
        return CropSageAgent._fallback_summary(service_result)

    @staticmethod
    def _remember(state: ConversationState, user_message: str, assistant_message: str) -> None:
        state.history.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ]
        )
        state.history = state.history[-MAX_HISTORY_MESSAGES:]

    @staticmethod
    def _response(
        session_id: str,
        status: str,
        message: str,
        *,
        missing_fields: list[str] | None = None,
        state: ConversationState | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "session_id": session_id,
            "message": message,
            "missing_fields": missing_fields or [],
            "collected_inputs": dict(state.inputs) if state else {},
            "recommendation": state.recommendation if state else None,
            "language_provider": state.language_provider if state else "not_used",
        }

    def close(self) -> None:
        close = getattr(self.gateway, "close", None)
        if callable(close):
            close()


def _load_crop_names() -> dict[str, str]:
    with CATALOG_PATH.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)
    return {crop["crop_id"]: crop["common_name"] for crop in catalog["crops"]}


def _clean_model_text(value: str) -> str:
    """Remove common transport artifacts without changing model meaning."""
    return value.replace("\ufffd", "–").strip()


def _load_dotenv_if_available() -> None:
    env_path = ROOT / ".env"
    try:
        from dotenv import load_dotenv
    except ImportError:
        if not env_path.is_file():
            return
        # Minimal fallback for agent settings only. It deliberately does
        # not attempt to implement the full dotenv format or load unrelated keys.
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            if key not in {
                "GEMINI_API_KEY",
                "GEMINI_MODEL",
                "OPEN_ROUTER_API_KEY",
                "OPENROUTER_API_KEY",
                "OPENROUTER_MODEL",
            } or key in os.environ:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key] = value
        return
    load_dotenv(env_path)


def main() -> None:
    try:
        agent = CropSageAgent()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print("CropSage agent is ready. Type 'exit' to stop or 'reset' to clear the assessment.")
    try:
        while True:
            user_message = input("Farmer: ").strip()
            if user_message.lower() in {"exit", "quit"}:
                break
            response = agent.chat(user_message)
            print(f"CropSage: {response['message']}")
    finally:
        agent.close()


if __name__ == "__main__":
    main()
