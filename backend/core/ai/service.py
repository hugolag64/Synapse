"""Façade de routage des tâches IA vers le modèle adapté."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from backend.core.ai.routing import AIImageContent, AIModel, AIResponse, AITask, model_for_task

MAX_CONTEXT_CHARS = 12_000


class AIClient(Protocol):
    def generate(
        self,
        prompt: str,
        model: AIModel,
        response_format: str = "text",
        response_schema: dict | None = None,
        *,
        images: Sequence[AIImageContent] = (),
    ) -> AIResponse:
        ...


class AIService:
    def __init__(self, client: AIClient) -> None:
        self.client = client

    def generate(
        self,
        task: AITask | str,
        prompt: str,
        *,
        context: str | None = None,
        response_format: str = "text",
        response_schema: dict | None = None,
        images: Sequence[AIImageContent] = (),
        difficulty=None,
    ) -> AIResponse:
        model = model_for_task(task, difficulty)
        full_prompt = prompt
        if context:
            bounded_context = context[:MAX_CONTEXT_CHARS]
            full_prompt = (
                f"{prompt}\n\n--- CONTEXTE DOCUMENTAIRE ---\n"
                f"{bounded_context}\n--- FIN CONTEXTE ---"
            )
        kwargs = {"task_name": str(task), "context": context}
        if response_schema is not None:
            kwargs["response_schema"] = response_schema
        if images:
            return self.client.generate(
                full_prompt,
                model,
                response_format,
                images=tuple(images),
                **kwargs,
            )
        return self.client.generate(
            full_prompt, model, response_format, **kwargs
        )
