import base64
import json
import logging

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .config import (
    PHOTO_LLM_API_KEY,
    PHOTO_LLM_BASE_URL,
    PHOTO_LLM_MODEL,
    PHOTO_LLM_REASONING_EFFORT,
    PHOTO_LLM_TIMEOUT_SECONDS,
)


logger = logging.getLogger(__name__)


class PhotoAnalysisError(Exception):
    pass


class MealPhotoItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=120)
    portion_g: float = Field(gt=0, le=3000)
    calories: int = Field(ge=0, le=10000)
    protein_g: float = Field(default=0, ge=0, le=500)
    carbs_g: float = Field(default=0, ge=0, le=500)
    fat_g: float = Field(default=0, ge=0, le=500)
    confidence: float = Field(default=0.5, ge=0, le=1)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Food name cannot be blank")
        return value[:120]

    @field_validator("portion_g", "protein_g", "carbs_g", "fat_g")
    @classmethod
    def round_macro(cls, value: float) -> float:
        return round(value, 1)


class MealPhotoResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[MealPhotoItem]


SYSTEM_PROMPT = """You estimate nutrition from meal photos for a calorie tracker.
Identify only distinct edible foods and drinks visible in the photo. Do not include
plates, bowls, utensils, hands, packaging, or background objects. Use Indian food
knowledge when relevant. Estimate the edible portion in grams and nutrition for
that portion, not per 100 g. Keep item names short, plain, and specific, such as
"Dal", "Steamed rice", or "Aloo fry". If several foods are mixed into one dish,
return one item for the dish. Be conservative when the portion size is uncertain.
Return at most 12 items. If no food is visible, return an empty items list.
portion_g must be one single estimated number for the edible portion.
Return only JSON matching: {"items":[{"name":string,"portion_g":number,
"calories":integer,"protein_g":number,"carbs_g":number,"fat_g":number,
"confidence":number}]}. confidence must be between 0 and 1."""


def _extract_json(content: str) -> object:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PhotoAnalysisError(
            "The photo analysis returned an unreadable result. Try another photo."
        ) from exc


async def _post_chat(
    client: httpx.AsyncClient, payload: dict
) -> dict:
    try:
        response = await client.post(
            f"{PHOTO_LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {PHOTO_LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    except httpx.TimeoutException as exc:
        raise PhotoAnalysisError(
            "Photo analysis timed out. Check the connection and try again."
        ) from exc
    except httpx.HTTPError as exc:
        raise PhotoAnalysisError(
            "Photo analysis is unavailable right now. Try again shortly."
        ) from exc

    if response.status_code in {401, 403}:
        raise PhotoAnalysisError(
            "Photo analysis is not configured correctly on this server."
        )
    if response.status_code == 429:
        raise PhotoAnalysisError(
            "Photo analysis is busy. Wait a minute and try again."
        )
    if response.is_error:
        raise PhotoAnalysisError(
            "Photo analysis is unavailable right now. Try again shortly."
        )

    try:
        return response.json()
    except ValueError as exc:
        raise PhotoAnalysisError(
            "The photo analysis returned an unreadable result. Try another photo."
        ) from exc


def _chat_message(body: dict) -> dict:
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise PhotoAnalysisError(
            "The photo analysis returned an unreadable result. Try another photo."
        ) from exc
    if not isinstance(message, dict):
        raise PhotoAnalysisError(
            "The photo analysis returned an unreadable result. Try another photo."
        )
    return message


def _log_empty_response(body: dict, attempt: str) -> None:
    try:
        choice = body["choices"][0]
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason")
        reasoning = message.get("reasoning_content")
    except (KeyError, IndexError, TypeError, AttributeError):
        finish_reason = None
        reasoning = None
    logger.warning(
        "DeepSeek returned empty photo analysis (%s): finish_reason=%s "
        "reasoning_chars=%s usage=%s",
        attempt,
        finish_reason,
        len(reasoning) if isinstance(reasoning, str) else 0,
        body.get("usage"),
    )


async def analyze_meal_photo(image: bytes, mime_type: str) -> list[MealPhotoItem]:
    if not PHOTO_LLM_API_KEY:
        raise PhotoAnalysisError("Photo analysis is not configured on this server.")

    encoded = base64.b64encode(image).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"
    payload = {
        "model": PHOTO_LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Analyze this meal photo and return the JSON nutrition "
                            "estimate."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "low"},
                    },
                ],
            },
        ],
        "response_format": {"type": "json_object"},
        "reasoning_effort": PHOTO_LLM_REASONING_EFFORT,
        "max_tokens": 1200,
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(PHOTO_LLM_TIMEOUT_SECONDS)
    ) as client:
        body = await _post_chat(client, payload)
        message = _chat_message(body)
        content = message.get("content")

        if not isinstance(content, str) or not content.strip():
            _log_empty_response(body, "json-mode")
            retry_payload = {
                **payload,
                "reasoning_effort": "none",
                "max_tokens": 1600,
            }
            retry_payload.pop("response_format", None)
            body = await _post_chat(client, retry_payload)
            message = _chat_message(body)
            content = message.get("content")

    if not isinstance(content, str) or not content.strip():
        _log_empty_response(body, "plain-mode")
        raise PhotoAnalysisError(
            "The photo analysis returned no result. Try another photo."
        )

    parsed = _extract_json(content)
    if isinstance(parsed, list):
        parsed = {"items": parsed}

    try:
        result = MealPhotoResult.model_validate(parsed)
    except ValidationError as exc:
        raise PhotoAnalysisError(
            "The photo analysis returned invalid nutrition data. Try another photo."
        ) from exc

    if not result.items:
        raise PhotoAnalysisError(
            "No food was detected in that photo. Move closer and try again."
        )
    return result.items[:12]
