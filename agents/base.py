"""Lightweight wrapper around the Anthropic Messages API."""
from __future__ import annotations

import os
import json
from anthropic import Anthropic


class BaseAgent:
    """One agent = one system prompt + one Claude conversation."""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        model: str | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.model = model or os.environ.get("CTA_MODEL", "claude-sonnet-4-6")
        self._client: Anthropic | None = None

    # lazy init so import doesn't crash when key is absent
    @property
    def client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic()
        return self._client

    # ── public API ─────────────────────────────────────
    def run(
        self,
        task: str,
        context: str | dict | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Send *task* (+ optional context) and return the text reply."""
        user_parts: list[str] = [task]
        if context is not None:
            blob = (
                context
                if isinstance(context, str)
                else json.dumps(context, ensure_ascii=False, default=str)
            )
            user_parts.append(f"\n\n<context>\n{blob}\n</context>")

        print(f"  [{self.name}] analysing ...")

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": "".join(user_parts)}],
        )

        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        print(f"  [{self.name}] done  (in:{in_tok} out:{out_tok})")
        return text
