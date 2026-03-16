"""
LLM Client — Unified interface for OpenAI / Anthropic / Google Gemini.
Set LLM_PROVIDER in .env to switch providers.
"""

import json
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()  # gemini (free) | openai | anthropic


def _strip_json_fence(text: str) -> str:
    """Remove markdown code fences around JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _call_openai(prompt: str, system: str, max_tokens: int) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    return response.choices[0].message.content


def _call_anthropic(prompt: str, system: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022"),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _call_gemini(prompt: str, system: str, max_tokens: int) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-04-17"),
        system_instruction=system,
    )
    response = model.generate_content(prompt)
    return response.text


def call_llm(prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 2000, retries: int = 3) -> str:
    """
    Unified LLM call with retry logic.
    Provider selected via LLM_PROVIDER env var.
    """
    for attempt in range(retries):
        try:
            if LLM_PROVIDER == "openai":
                return _call_openai(prompt, system, max_tokens)
            elif LLM_PROVIDER == "anthropic":
                return _call_anthropic(prompt, system, max_tokens)
            elif LLM_PROVIDER == "gemini":
                return _call_gemini(prompt, system, max_tokens)
            else:
                raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")
        except Exception as e:
            logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
            else:
                raise


def call_llm_json(prompt: str, system: str, max_tokens: int = 2000) -> Any:
    """
    Call LLM and parse JSON response. Strips fences and retries on bad JSON.
    """
    raw = call_llm(prompt, system, max_tokens)
    cleaned = _strip_json_fence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse failed. Raw response:\n{raw}\nError: {e}")
        raise ValueError(f"LLM returned invalid JSON: {e}")
