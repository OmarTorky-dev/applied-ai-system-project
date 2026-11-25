"""LLM clients that turn a diagnosis prompt into a structured FixProposal.

- ClaudeClient   calls the Claude API (needs ANTHROPIC_API_KEY).
- RecordingClient wraps ClaudeClient and saves every response to recordings/.
- ReplayClient   answers from recordings/ with no network, so anyone can reproduce the
                 documented runs without an API key.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

log = logging.getLogger("glitch_ai.llm")

MODEL = "claude-opus-5-5"
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


class RecordingClient:
    """Calls Claude and stores each (prompt -> proposal) pair for later replay."""

    def __init__(self, inner: ClaudeClient, directory: Path = RECORDINGS_DIR):
        self.inner = inner
        self.directory = directory
        self.name = inner.name + " [recording]"

    def propose_fix(self, system: str, prompt: str) -> FixProposal:
        proposal = self.inner.propose_fix(system, prompt)
        self.directory.mkdir(exist_ok=True)
        path = self.directory / f"{prompt_key(system, prompt)}.json"
        path.write_text(
            json.dumps({"model": MODEL, "proposal": proposal.model_dump()}, indent=2),
            encoding="utf-8",
        )
        return proposal


class ReplayClient:
    """Deterministic, offline: returns the recorded Claude response for an identical prompt."""

    name = "replay (recorded Claude responses)"

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


def make_client(mode: str = "auto") -> LLMClient:
    """mode: 'live', 'record', 'replay', or 'auto' (live if a key is set, else replay)."""
    if mode == "auto":
        mode = "live" if os.environ.get("ANTHROPIC_API_KEY") else "replay"
    if mode == "replay":
        return ReplayClient()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMError("ANTHROPIC_API_KEY is not set. Add it to .env or use --mode replay.")
    if mode == "record":
        return RecordingClient(ClaudeClient())
    if mode == "live":
        return ClaudeClient()
    raise ValueError(f"Unknown mode: {mode}")
