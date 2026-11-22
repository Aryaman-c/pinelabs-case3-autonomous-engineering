import json
import time
import uuid
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import structlog
from google import genai
from google.genai import types

from orchestrator.state import TraceEntry, WorkflowState

log = structlog.get_logger()

COST_MAP = {
    "gemini-2.0-flash-exp": (0.000000075, 0.0000003),
    "gemini-2.0-pro-exp": (0.00000125, 0.000005),
}


class BaseAgent(ABC):
    model: str = "gemini-2.0-flash-exp"
    node_name: str = "base"
    max_json_retries: int = 2

    def __init__(self, client: genai.Client | None = None):
        self._custom_client = client
        if client is not None:
            self.client = client
        else:
            api_key = os.environ.get("GEMINI_API_KEY", "")
            self._cached_key = api_key
            self.client = genai.Client(api_key=api_key or "DUMMY_KEY")

    def get_client(self) -> genai.Client:
        if self._custom_client is not None:
            return self._custom_client
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not hasattr(self, "_cached_key") or self._cached_key != api_key:
            self._cached_key = api_key
            self.client = genai.Client(api_key=api_key or "DUMMY_KEY")
        return self.client

    @abstractmethod
    def build_prompt(self, state: WorkflowState) -> str: ...

    @abstractmethod
    def parse_output(self, raw: str) -> dict: ...

    @abstractmethod
    def state_update(self, parsed: dict, state: WorkflowState) -> dict: ...

    def __call__(self, state: WorkflowState) -> dict:
        started_at = datetime.now(timezone.utc)
        start_ms = time.monotonic_ns() // 1_000_000
        attempt = 0
        last_error = None
        parsed = None
        input_tokens = output_tokens = 0

        prompt = self.build_prompt(state)

        client = self.get_client()
        active_model = self.model
        if self.node_name in ("ARCHITECTURE", "DEVELOPMENT"):
            active_model = os.environ.get("GEMINI_MODEL_SMART", self.model)
        elif self.node_name in ("ANALYSIS", "TEST_WRITING", "RELEASE_PREP"):
            active_model = os.environ.get("GEMINI_MODEL_FAST", self.model)

        while attempt <= self.max_json_retries:
            try:
                contents = prompt if attempt == 0 else f"{prompt}\n\nSchema Fix: previous response failed parsing: {last_error}"
                response = client.models.generate_content(
                    model=active_model,
                    contents=contents,
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
                )
                raw_text = response.text or "{}"
                if response.usage_metadata:
                    input_tokens = response.usage_metadata.prompt_token_count or 0
                    output_tokens = response.usage_metadata.candidates_token_count or 0
                parsed = self.parse_output(raw_text)
                break
            except Exception as e:
                last_error = str(e)
                log.warning("agent.retry", node=self.node_name, attempt=attempt, error=last_error)
                attempt += 1

        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
        rates = COST_MAP.get(self.model, (0.0, 0.0))
        cost_usd = (input_tokens * rates[0]) + (output_tokens * rates[1])

        trace_entry: TraceEntry = {
            "node": self.node_name,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "model": self.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "status": "success" if parsed else "error",
            "error": last_error if not parsed else None,
        }

        history_entry = {
            "id": str(uuid.uuid4()),
            "node": self.node_name,
            "timestamp": started_at.isoformat(),
            "status": "success" if parsed else "failed",
        }

        # FAIL FAST: Do not allow None to cascade downstream
        if parsed is None:
            raise RuntimeError(
                f"Agent {self.node_name} failed to return a valid schema after {self.max_json_retries} attempts: {last_error}"
            )

        updates = self.state_update(parsed, state)
        updates["current_node"] = self.node_name
        updates["agent_history"] = [history_entry]
        updates["trace_log"] = [trace_entry]
        return updates
