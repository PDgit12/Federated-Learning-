from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import msal
import requests

from .config import settings


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


@dataclass
class GraphMessage:
    id: str
    subject: str
    from_name: str
    from_email: str
    to_emails: List[str]
    cc_emails: List[str]
    received_datetime: str
    conversation_id: Optional[str]
    internet_message_id: Optional[str]
    body_preview: Optional[str]
    body_content_type: str
    body_content: str


class GraphClient:
    def __init__(self, client_id: str, tenant: str, scopes: List[str], token_cache_path: str) -> None:
        self.client_id = client_id
        self.tenant = tenant
        self.scopes = scopes
        self.token_cache_path = token_cache_path

        os.makedirs(os.path.dirname(self.token_cache_path), exist_ok=True)

        self.cache = msal.SerializableTokenCache()
        if os.path.exists(self.token_cache_path):
            try:
                self.cache.deserialize(open(self.token_cache_path, "r").read())
            except Exception:
                pass

        self.app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant}",
            token_cache=self.cache,
        )

    def _persist_cache(self) -> None:
        if self.cache.has_state_changed:
            with open(self.token_cache_path, "w") as f:
                f.write(self.cache.serialize())

    def acquire_token(self) -> Dict:
        accounts = self.app.get_accounts()
        result: Optional[Dict] = None
        if accounts:
            result = self.app.acquire_token_silent(scopes=self.scopes, account=accounts[0])
        if not result:
            flow = self.app.initiate_device_flow(scopes=self.scopes)
            if "user_code" not in flow:
                raise RuntimeError("Failed to create device flow. Check app registration allows public client flows.")
            print("To sign in, use a web browser to open the page and enter the code:")
            print(flow["verification_uri"])
            print("Code:", flow["user_code"])
            result = self.app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Token acquisition failed: {result}")
        self._persist_cache()
        return result

    def _get_headers(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def iter_messages(self, folder: Optional[str] = None) -> Iterable[GraphMessage]:
        token = self.acquire_token()["access_token"]
        url = f"{GRAPH_BASE}/me/messages"
        if folder:
            url = f"{GRAPH_BASE}/me/mailFolders/{folder}/messages"
        params = {
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,conversationId,internetMessageId,bodyPreview,body,body/contentType",
            "$orderby": "receivedDateTime desc",
            "$top": 50,
        }
        session = requests.Session()
        while url:
            resp = session.get(url, headers=self._get_headers(token), params=params)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("value", []):
                from_email = ""
                from_name = ""
                if item.get("from") and item["from"].get("emailAddress"):
                    from_email = item["from"]["emailAddress"].get("address", "")
                    from_name = item["from"]["emailAddress"].get("name", "")
                to_emails = [
                    r["emailAddress"].get("address", "")
                    for r in (item.get("toRecipients") or [])
                    if r.get("emailAddress")
                ]
                cc_emails = [
                    r["emailAddress"].get("address", "")
                    for r in (item.get("ccRecipients") or [])
                    if r.get("emailAddress")
                ]
                body = item.get("body") or {}
                body_content_type = body.get("contentType", "text")
                body_content = body.get("content", "")

                yield GraphMessage(
                    id=item.get("id"),
                    subject=item.get("subject") or "",
                    from_name=from_name,
                    from_email=from_email,
                    to_emails=to_emails,
                    cc_emails=cc_emails,
                    received_datetime=item.get("receivedDateTime") or "",
                    conversation_id=item.get("conversationId"),
                    internet_message_id=item.get("internetMessageId"),
                    body_preview=item.get("bodyPreview"),
                    body_content_type=body_content_type,
                    body_content=body_content,
                )
            url = data.get("@odata.nextLink")
            params = None  # Next links include everything

