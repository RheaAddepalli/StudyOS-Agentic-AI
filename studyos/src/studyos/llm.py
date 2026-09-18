"""Thin wrapper around the Groq SDK.

Keeps two things separate on purpose: `complete()` for free-text reasoning,
and `complete_json()` for anything that must come back as a specific schema
— curriculum stages, evaluation scores, etc.
"""

from __future__ import annotations

import json
import time
from typing import Type, TypeVar

from groq import Groq, RateLimitError
from pydantic import BaseModel

from .config import settings

T = TypeVar("T", bound=BaseModel)

_client: Groq | None = None


def get_client() -> Groq:
    global _client
    if _client is None:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def complete(prompt: str, system: str = "", max_tokens: int = 2000, _retries: int = 4) -> str:
    """Calls Groq, automatically retrying on rate limits (HTTP 429) — but only
    up to a short cap. Groq's error sometimes includes a suggested wait time
    that can be long (once you're well past a quota, not just a per-minute
    limit), and blindly honoring that on an interactive request would hang
    a button click for minutes with zero feedback. Past MAX_WAIT_SECONDS we
    fail fast with a clear message instead of sleeping."""
    MAX_WAIT_SECONDS = 12.0

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(_retries + 1):
        try:
            resp = get_client().chat.completions.create(
                model=settings.model,
                max_tokens=max_tokens,
                messages=messages,
            )
            return resp.choices[0].message.content or ""
        except RateLimitError as e:
            wait_s = _extract_retry_after(e) or (2 ** attempt)
            if wait_s > MAX_WAIT_SECONDS or attempt == _retries:
                raise RuntimeError(
                    "The AI provider is rate-limited right now (Groq's free tier "
                    "has a usage cap). Wait a bit and try again."
                ) from e
            time.sleep(wait_s)


def _extract_retry_after(error: RateLimitError) -> float | None:
    try:
        header = error.response.headers.get("retry-after")
        return float(header) if header else None
    except Exception:
        return None


def complete_json(prompt: str, schema: Type[T], system: str = "", max_tokens: int = 2000) -> T:
    """Ask the model for JSON matching `schema` and validate it. Retries once
    with the validation error fed back to the model."""
    schema_hint = json.dumps(schema.model_json_schema(), indent=2)
    full_system = (
        f"{system}\n\n"
        "Respond with ONLY a single JSON object matching this schema. "
        "No markdown fences, no preamble, no explanation outside the JSON.\n"
        f"{schema_hint}"
    )

    text = complete(prompt, system=full_system, max_tokens=max_tokens)
    try:
        return schema.model_validate_json(_strip_fences(text))
    except Exception as first_error:
        repair_prompt = (
            f"Your previous response failed validation with this error:\n{first_error}\n\n"
            f"Previous response:\n{text}\n\n"
            "Return corrected JSON only, matching the schema exactly."
        )
        text2 = complete(repair_prompt, system=full_system, max_tokens=max_tokens)
        return schema.model_validate_json(_strip_fences(text2))


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    return t.strip()


















# """Thin wrapper around the Anthropic SDK.

# Keeps two things separate on purpose (see README "Evidence and reliability"):
# `complete()` for free-text reasoning, and `complete_json()` for anything that
# must come back as a specific schema — curriculum stages, evaluation scores,
# etc. Every node that calls `complete_json` is doing model reasoning, not
# retrieval; the caller is responsible for tagging results with
# EvidenceTag.MODEL_GENERATED when they get stored.
# """

# from __future__ import annotations

# import json
# import time
# from typing import Type, TypeVar

# from groq import Groq, RateLimitError
# from pydantic import BaseModel

# from .config import settings
# T = TypeVar("T", bound=BaseModel)

# _client: Groq | None = None


# def get_client() -> Groq:
#     global _client
#     if _client is None:
#         if not settings.groq_api_key:
#             raise RuntimeError(
#                 "GROQ_API_KEY is not set. Copy .env.example to .env and fill it in."
#             )
#         _client = Groq(api_key=settings.groq_api_key)
#     return _client


# def complete(prompt: str, system: str = "", max_tokens: int = 2000, _retries: int = 4) -> str:
#     """Calls Groq, automatically retrying on rate limits (HTTP 429). Groq's
#     free tier caps tokens-per-minute fairly low, and a 23-concept curriculum
#     can genuinely burst past that within a run — without this, one 429 would
#     kill the whole pipeline after several minutes of otherwise-successful
#     work. Reads Groq's own suggested wait time from the error when present,
#     falls back to exponential backoff otherwise."""
#     messages = []
#     if system:
#         messages.append({"role": "system", "content": system})
#     messages.append({"role": "user", "content": prompt})

#     for attempt in range(_retries + 1):
#         try:
#             resp = get_client().chat.completions.create(
#                 model=settings.model,
#                 max_tokens=max_tokens,
#                 messages=messages,
#             )
#             return resp.choices[0].message.content or ""
#         except RateLimitError as e:
#             if attempt == _retries:
#                 raise
#             wait_s = _extract_retry_after(e) or (2 ** attempt)
#             time.sleep(wait_s)


# def _extract_retry_after(error: RateLimitError) -> float | None:
#     try:
#         header = error.response.headers.get("retry-after")
#         return float(header) if header else None
#     except Exception:
#         return None


# def complete_json(prompt: str, schema: Type[T], system: str = "", max_tokens: int = 2000) -> T:
#     """Ask the model for JSON matching `schema` and validate it. Retries once
#     with the validation error fed back to the model — LLMs are much better at
#     fixing malformed JSON when shown exactly what was wrong than at getting it
#     right blind on the first try."""
#     schema_hint = json.dumps(schema.model_json_schema(), indent=2)
#     full_system = (
#         f"{system}\n\n"
#         "Respond with ONLY a single JSON object matching this schema. "
#         "No markdown fences, no preamble, no explanation outside the JSON.\n"
#         f"{schema_hint}"
#     )

#     text = complete(prompt, system=full_system, max_tokens=max_tokens)
#     try:
#         return schema.model_validate_json(_strip_fences(text))
#     except Exception as first_error:
#         repair_prompt = (
#             f"Your previous response failed validation with this error:\n{first_error}\n\n"
#             f"Previous response:\n{text}\n\n"
#             "Return corrected JSON only, matching the schema exactly."
#         )
#         text2 = complete(repair_prompt, system=full_system, max_tokens=max_tokens)
#         return schema.model_validate_json(_strip_fences(text2))


# def _strip_fences(text: str) -> str:
#     t = text.strip()
#     if t.startswith("```"):
#         t = t.split("```")[1]
#         if t.startswith("json"):
#             t = t[4:]
#     return t.strip()
