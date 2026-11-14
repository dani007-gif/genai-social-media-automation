"""Gmail API intake: find new request emails, fetch them, and mark them processed."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Iterator, List, Optional

from .models import IncomingEmail
from .parser import parse_raw_email

# gmail.modify = read messages + add/remove labels (needed to mark emails as processed).
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
PROCESSED_LABEL = "smm-processed"


class GmailIntake:
    def __init__(
        self,
        credentials_file: str = "credentials.json",
        token_file: str = "token.json",
        attachments_dir: str = "data/attachments",
    ):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.attachments_dir = Path(attachments_dir)
        self._service = None
        self._label_id: Optional[str] = None

    # ---------- auth ----------
    @property
    def service(self):
        if self._service is None:
            self._service = self._build_service()
        return self._service

    def _build_service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if Path(self.token_file).exists():
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not Path(self.credentials_file).exists():
                    raise FileNotFoundError(
                        f"{self.credentials_file} not found. Download an OAuth 'Desktop app' client "
                        "from Google Cloud Console (APIs & Services > Credentials) and save it here."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            Path(self.token_file).write_text(creds.to_json())
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    # ---------- fetching ----------
    def list_new_message_ids(self, query: str = "", max_results: int = 10) -> List[str]:
        """Unread emails not yet processed. `query` uses Gmail search syntax, e.g. 'to:posts@acme.com'."""
        q = f"is:unread -label:{PROCESSED_LABEL} {query}".strip()
        resp = (
            self.service.users()
            .messages()
            .list(userId="me", q=q, maxResults=max_results)
            .execute()
        )
        return [m["id"] for m in resp.get("messages", [])]

    def fetch(self, message_id: str) -> IncomingEmail:
        msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="raw")
            .execute()
        )
        raw = base64.urlsafe_b64decode(msg["raw"].encode("ascii"))
        return parse_raw_email(
            raw,
            message_id=message_id,
            thread_id=msg.get("threadId"),
            attachments_dir=self.attachments_dir,
            source="gmail",
        )

    def fetch_new(self, query: str = "", max_results: int = 10) -> Iterator[IncomingEmail]:
        for mid in self.list_new_message_ids(query=query, max_results=max_results):
            yield self.fetch(mid)

    # ---------- bookkeeping ----------
    def mark_processed(self, message_id: str, mark_read: bool = True) -> None:
        """Label the email so it isn't picked up again. Call this once the pipeline has accepted it."""
        body = {"addLabelIds": [self._get_or_create_label()]}
        if mark_read:
            body["removeLabelIds"] = ["UNREAD"]
        self.service.users().messages().modify(userId="me", id=message_id, body=body).execute()

    def _get_or_create_label(self) -> str:
        if self._label_id:
            return self._label_id
        labels = self.service.users().labels().list(userId="me").execute().get("labels", [])
        for lbl in labels:
            if lbl["name"] == PROCESSED_LABEL:
                self._label_id = lbl["id"]
                return self._label_id
        created = (
            self.service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": PROCESSED_LABEL,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        self._label_id = created["id"]
        return self._label_id
