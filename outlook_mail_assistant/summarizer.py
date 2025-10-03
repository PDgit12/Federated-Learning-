from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from .config import settings
from .utils import collapse_whitespace, truncate


@dataclass
class SummaryResult:
    summary: str
    model: str


class BaseSummarizer:
    def summarize(self, subject: str, body_text: str, max_tokens: int) -> SummaryResult:
        raise NotImplementedError


class NaiveSummarizer(BaseSummarizer):
    def summarize(self, subject: str, body_text: str, max_tokens: int) -> SummaryResult:
        sentences = [s.strip() for s in body_text.split(". ") if s.strip()]
        selected = sentences[:5]
        summary = subject.strip()
        if summary:
            summary = f"Subject: {summary}. "
        summary += " ".join(selected)
        return SummaryResult(summary=truncate(summary, 1200), model="naive")


class OpenAISummarizer(BaseSummarizer):
    def __init__(self) -> None:
        from openai import OpenAI  # lazy import

        client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        self.client = client
        self.model = settings.openai_model

    def summarize(self, subject: str, body_text: str, max_tokens: int) -> SummaryResult:
        prompt = (
            "You are an assistant that summarizes email messages for quick triage. "
            "Write a concise bullet-style summary with key facts, dates, numbers, decisions, and actions. "
            "Include sender and subject context if helpful. Keep it under 8 bullets."
        )
        content = f"Subject: {subject}\n\nEmail:\n{body_text}"
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        text = resp.choices[0].message.content.strip()
        return SummaryResult(summary=text, model=self.model)


def get_summarizer() -> BaseSummarizer:
    if settings.openai_api_key:
        try:
            return OpenAISummarizer()
        except Exception:
            pass
    return NaiveSummarizer()
