from __future__ import annotations

import sys
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from .config import settings
from .db import Database
from .graph import GraphClient
from .summarizer import get_summarizer
from .utils import html_to_text, truncate

console = Console()


@click.group()
def cli() -> None:
    """Outlook Mail Assistant: sync, search, and summarize your Outlook emails."""


@cli.command()
@click.option("--folder", default=None, help="Specific folder id or well-known name (e.g., Inbox)")
@click.option("--limit", default=None, type=int, help="Limit number of messages to fetch (for testing)")
@click.option("--no-summarize", is_flag=True, help="Skip summarization during sync")
def sync(folder: Optional[str], limit: Optional[int], no_summarize: bool) -> None:
    """Fetch emails from Outlook and store in local DB; summarize new ones."""
    if not settings.ms_client_id:
        console.print("[red]MS_CLIENT_ID is not set. Configure environment and retry.[/red]")
        sys.exit(1)

    db = Database(settings.db_path)
    client = GraphClient(
        client_id=settings.ms_client_id,
        tenant=settings.ms_tenant_id,
        scopes=[s.strip() for s in settings.ms_scopes.split(",") if s.strip()],
        token_cache_path=settings.token_cache_path,
    )

    summarizer = None if no_summarize else get_summarizer()

    count = 0
    for msg in client.iter_messages(folder=folder):
        body_text = msg.body_content if msg.body_content_type.lower() == "text" else html_to_text(msg.body_content)
        db.upsert_email(
            id=msg.id,
            subject=msg.subject or "",
            from_name=msg.from_name or "",
            from_email=msg.from_email or "",
            to_emails=msg.to_emails or [],
            cc_emails=msg.cc_emails or [],
            received_datetime=msg.received_datetime or "",
            conversation_id=msg.conversation_id,
            internet_message_id=msg.internet_message_id,
            body_preview=msg.body_preview or "",
            body_text=body_text,
            body_content_type=msg.body_content_type or "",
        )
        count += 1
        if limit and count >= limit:
            break

    console.print(f"[green]Synced {count} messages.[/green]")

    if not no_summarize:
        summarizer = summarizer or get_summarizer()
        summarized = 0
        for row in db.iter_without_summary(limit=5000):
            result = summarizer.summarize(row["subject"] or "", row["body_text"] or "", settings.summary_max_tokens)
            db.set_summary(row["id"], result.summary)
            summarized += 1
        console.print(f"[green]Summarized {summarized} new messages.[/green]")


@cli.command()
@click.argument("query", nargs=-1)
@click.option("--limit", default=5, type=int)
def ask(query: tuple[str, ...], limit: int) -> None:
    """Ask about emails; returns best matches and their summaries."""
    q = " ".join(query).strip()
    if not q:
        console.print("[red]Provide a query, e.g.,: ask invoice from Acme July[/red]")
        return

    db = Database(settings.db_path)
    rows = db.search(q, limit=limit)

    if not rows:
        console.print("[yellow]No matches found.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#")
    table.add_column("From")
    table.add_column("Subject")
    table.add_column("Received")
    table.add_column("Summary")

    for idx, row in enumerate(rows, start=1):
        table.add_row(
            str(idx),
            f"{row['from_name']} <{row['from_email']}>",
            row["subject"] or "",
            row["received_datetime"] or "",
            truncate(row["summary"] or row["body_preview"] or "", 200),
        )

    console.print(table)
    console.print("Use: show <number> to see full summary and details.")

    # Cache last results for immediate show by number
    global _last_results
    _last_results = [r["id"] for r in rows]


_last_results: list[str] = []


@cli.command()
@click.argument("selector")
def show(selector: str) -> None:
    """Show a specific email by index from last ask, or by message id."""
    db = Database(settings.db_path)

    message_id = selector
    if selector.isdigit() and _last_results:
        idx = int(selector) - 1
        if 0 <= idx < len(_last_results):
            message_id = _last_results[idx]

    row = db.get_email(message_id)
    if not row:
        console.print(f"[red]Email not found: {selector}[/red]")
        return

    console.rule("Email")
    console.print(f"[bold]From:[/bold] {row['from_name']} <{row['from_email']}>")
    console.print(f"[bold]Subject:[/bold] {row['subject']}")
    console.print(f"[bold]Received:[/bold] {row['received_datetime']}")

    console.rule("Summary")
    console.print(row["summary"] or "(No summary yet)")

    console.rule("Preview")
    console.print(truncate(row["body_text"] or "", 2000))


if __name__ == "__main__":
    cli()
