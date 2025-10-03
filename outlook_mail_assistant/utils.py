from __future__ import annotations

import re
from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup(["script", "style"]):
        script.decompose()
    text = soup.get_text(separator="\n")
    return collapse_whitespace(text)


def collapse_whitespace(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[\t ]+", " ", text)
    return text.strip()


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)] + "…"
