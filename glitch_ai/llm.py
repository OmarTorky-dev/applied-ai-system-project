"""LLM clients that turn a diagnosis prompt into a structured FixProposal.

- GeminiClient   calls Google Gemini (needs GEMINI_API_KEY). Used for the documented runs.
- ClaudeClient   calls the Claude API (needs ANTHROPIC_API_KEY).
- RecordingClient wraps either client and saves every response to recordings/.
- ReplayClient   answers from recordings/ with no network, so anyone can reproduce the
                 documented runs without an API key.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

log = logging.getLogger("glitch_ai.llm")

MODEL = "claude-opus-5-5"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recordings"


class FixProposal(BaseModel):
    diagnosis: str = Field(description="Root cause of each failing test, in plain English.")
    cited_patterns: list[str] = Field(
        description="IDs of the knowledge-base documents (e.g. KB01) the fix relies on."
    )
    changes: list[str] = Field(description="One short bullet per change made to the code.")
    fixed_code: str = Field(description="The complete corrected logic_utils.py file.")
    confidence: float = Field(description="Self-rated confidence from 0.0 to 1.0 that all tests will pass.")


class LLMError(RuntimeError):
    """Raised when the model cannot produce a usable proposal."""


class LLMClient(Protocol):
    name: str

    def propose_fix(self, system: str, prompt: str) -> FixProposal: ...


def prompt_key(system: str, prompt: str) -> str:
    return hashlib.sha256((system + "\n\n" + prompt).encode("utf-8")).hexdigest()[:16]


class ClaudeClient:
    name = f"claude ({MODEL})"

    def __init__(self, effort: str = "medium"):
        import anthropic  # imported lazily so replay mode works without the SDK configured

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(max_retries=3, timeout=180.0)
        self.effort = effort

    def propose_fix(self, system: str, prompt: str) -> FixProposal:
        a = self._anthropic
        try:
            response = self._client.beta.messages.parse(
                model=MODEL,
                max_tokens=16000,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
                output_format=FixProposal,
                output_config={"effort": self.effort},
                # If a safety classifier declines, retry on a fallback model in the same call.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except a.AuthenticationError as exc:
            raise LLMError("Invalid or missing ANTHROPIC_API_KEY.") from exc
        except a.RateLimitError as exc:
            raise LLMError("Rate limited by the Claude API; try again shortly.") from exc
        except a.APIStatusError as exc:
            raise LLMError(f"Claude API error {exc.status_code}: {exc.message}") from exc
        except a.APIConnectionError as exc:
            raise LLMError("Could not reach the Claude API (network error).") from exc

        log.info(
            "claude call: request_id=%s stop=%s in=%s out=%s",
            response._request_id, response.stop_reason,
            response.usage.input_tokens, response.usage.output_tokens,
        )
        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The model's answer was cut off (max_tokens).")
        if response.parsed_output is None:
            raise LLMError("The model did not return a valid FixProposal.")
        return response.parsed_output


class GeminiClient:
    """Google Gemini with JSON-schema structured output (response_schema=FixProposal)."""

    RETRYABLE = {429, 500, 503, 504}

    def __init__(self, model: str = GEMINI_MODEL, retries: int = 4):
        from google import genai
        from google.genai import errors

        self._errors = errors
        self._client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options={"timeout": 180_000},  # milliseconds
        )
        self.model = model
        self.retries = retries
        self.name = f"gemini ({model})"

    def propose_fix(self, system: str, prompt: str) -> FixProposal:
        config = {
            "system_instruction": system,
            "response_mime_type": "application/json",
            "response_schema": FixProposal,
            "temperature": 0.2,
        }
        for attempt in range(1, self.retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=prompt, config=config)
                break
            except self._errors.APIError as exc:
                if exc.code in self.RETRYABLE and attempt < self.retries:
                    wait = 5 * 2 ** (attempt - 1)
                    log.warning("gemini %s (attempt %d), retrying in %ds", exc.code, attempt, wait)
                    time.sleep(wait)
                    continue
                if exc.code in (401, 403):
                    raise LLMError("Invalid or unauthorized GEMINI_API_KEY.") from exc
                raise LLMError(f"Gemini API error {exc.code}: {exc.message}") from exc
            except Exception as exc:  # network failures, timeouts
                raise LLMError(f"Could not reach the Gemini API: {exc}") from exc

        usage = response.usage_metadata
        log.info("gemini call: model=%s in=%s out=%s", self.model,
                 getattr(usage, "prompt_token_count", "?"),
                 getattr(usage, "candidates_token_count", "?"))
        parsed = response.parsed
        if parsed is None:
            try:
                parsed = FixProposal.model_validate_json(response.text or "")
            except Exception as exc:
                raise LLMError("The model did not return a valid FixProposal.") from exc
        return parsed


class RecordingClient:
    """Calls Claude and stores each (prompt -> proposal) pair for later replay."""

    def __init__(self, inner: LLMClient, directory: Path = RECORDINGS_DIR):
        self.inner = inner
        self.directory = directory
        self.name = inner.name + " [recording]"

    def propose_fix(self, system: str, prompt: str) -> FixProposal:
        proposal = self.inner.propose_fix(system, prompt)
        self.directory.mkdir(exist_ok=True)
        path = self.directory / f"{prompt_key(system, prompt)}.json"
        path.write_text(
            json.dumps({"model": self.inner.name, "proposal": proposal.model_dump()}, indent=2),
            encoding="utf-8",
        )
        return proposal


class ReplayClient:
    """Deterministic, offline: returns the recorded Claude response for an identical prompt."""

    name = "replay (recorded model responses)"

    def __init__(self, directory: Path = RECORDINGS_DIR):
        self.directory = directory

    def propose_fix(self, system: str, prompt: str) -> FixProposal:
        path = self.directory / f"{prompt_key(system, prompt)}.json"
        if not path.exists():
            raise LLMError(
                f"No recording for this prompt ({path.name}). Replay only covers the "
                "bundled samples; set ANTHROPIC_API_KEY and use --mode live for new code."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return FixProposal.model_validate(data["proposal"])


def _live_client(provider: str) -> LLMClient:
    if provider == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            provider = "claude"
        elif os.environ.get("GEMINI_API_KEY"):
            provider = "gemini"
        else:
            raise LLMError("No API key found. Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env, "
                           "or use --mode replay.")
    if provider == "gemini":
        if not os.environ.get("GEMINI_API_KEY"):
            raise LLMError("GEMINI_API_KEY is not set.")
        return GeminiClient()
    if provider == "claude":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMError("ANTHROPIC_API_KEY is not set.")
        return ClaudeClient()
    raise ValueError(f"Unknown provider: {provider}")


def make_client(mode: str = "auto", provider: str = "auto") -> LLMClient:
    """mode: 'live', 'record', 'replay', or 'auto' (live if any key is set, else replay).
    provider: 'gemini', 'claude', or 'auto' (whichever key is present; Claude first)."""
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GEMINI_API_KEY"))
    if mode == "auto":
        mode = "live" if has_key else "replay"
    if mode == "replay":
        return ReplayClient()
    if mode == "record":
        return RecordingClient(_live_client(provider))
    if mode == "live":
        return _live_client(provider)
    raise ValueError(f"Unknown mode: {mode}")
