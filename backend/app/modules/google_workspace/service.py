"""Server-side Google Workspace OAuth and API helpers.

Tokens are never returned to browsers, persisted in audit data, or exposed to the
AI provider. All calls use a short-lived access token refreshed from encrypted
server storage.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.google_workspace.models import (
    GoogleOAuthAttempt,
    GoogleWorkspaceConnection,
    GoogleWorkspaceResource,
)


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
FORMS_API = "https://forms.googleapis.com/v1"
SHEETS_API = "https://sheets.googleapis.com/v4"
DRIVE_API = "https://www.googleapis.com/drive/v3"
SCOPES = (
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
)


class GoogleWorkspaceError(Exception):
    def __init__(self, detail: str, status_code: int = 422):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def configured() -> bool:
    return bool(
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_redirect_uri
        and settings.google_allowed_workspace_domain
    )


def require_configuration() -> None:
    if not configured():
        raise GoogleWorkspaceError("Google Workspace OAuth is not configured on this server.", 503)


def _fernet() -> Fernet:
    # A separate key is preferred. The JWT key fallback keeps existing installs
    # encrypted while the administrator adds GOOGLE_TOKEN_ENCRYPTION_KEY.
    source = settings.google_token_encryption_key or settings.jwt_secret_key
    key = base64.urlsafe_b64encode(hashlib.sha256(source.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_refresh_token(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_refresh_token(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise GoogleWorkspaceError("The saved Google connection cannot be decrypted. Reconnect it.", 409) from exc


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def create_oauth_attempt(db: Session, *, user_id: int, college_id: int) -> str:
    require_configuration()
    now = utcnow()
    db.execute(delete(GoogleOAuthAttempt).where(GoogleOAuthAttempt.expires_at < now))
    state = secrets.token_urlsafe(32)
    db.add(
        GoogleOAuthAttempt(
            state_hash=_state_hash(state),
            user_id=user_id,
            college_id=college_id,
            expires_at=now + timedelta(seconds=settings.google_oauth_state_ttl_seconds),
        )
    )
    return state


def authorization_url(state: str) -> str:
    require_configuration()
    query = urlencode(
        {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            # Consent makes a refresh-token re-authorization explicit, rather
            # than silently depending on a past Google grant.
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{GOOGLE_AUTH_URL}?{query}"


def consume_oauth_attempt(db: Session, state: str | None) -> GoogleOAuthAttempt:
    if not state:
        raise GoogleWorkspaceError("Missing OAuth state.", 400)
    attempt = db.get(GoogleOAuthAttempt, _state_hash(state))
    if attempt is None:
        raise GoogleWorkspaceError("This Google authorization link is invalid or was already used.", 400)
    expires_at = attempt.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= utcnow():
        db.delete(attempt)
        db.commit()
        raise GoogleWorkspaceError("This Google authorization link expired. Start again.", 400)
    db.delete(attempt)
    # Commit before contacting Google so state is genuinely single-use even if
    # the code exchange is retried or an upstream request times out.
    db.commit()
    return attempt


def _request(method: str, url: str, **kwargs: Any) -> httpx.Response:
    try:
        return httpx.request(method, url, timeout=settings.google_workspace_timeout_seconds, **kwargs)
    except httpx.TimeoutException as exc:
        raise GoogleWorkspaceError(
            "Google Workspace did not respond before the server timeout. Try again; if this continues, check the backend's outbound internet access.",
            504,
        ) from exc
    except httpx.RequestError as exc:
        raise GoogleWorkspaceError(
            "The server could not contact Google Workspace. Check the backend's internet connection and Google service availability.",
            502,
        ) from exc


def _error_detail(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return fallback
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or fallback)
    return str(error or fallback)


def _token_request(data: dict[str, str]) -> dict[str, Any]:
    response = _request("POST", GOOGLE_TOKEN_URL, data=data)
    if response.is_error:
        raise GoogleWorkspaceError("Google could not complete the authorization. Please connect again.", 400)
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise GoogleWorkspaceError("Google returned an incomplete authorization response.", 400)
    return payload


def exchange_code(code: str) -> tuple[dict[str, Any], str]:
    require_configuration()
    token = _token_request(
        {
            "code": code,
            "client_id": settings.google_oauth_client_id or "",
            "client_secret": settings.google_oauth_client_secret or "",
            "redirect_uri": settings.google_oauth_redirect_uri or "",
            "grant_type": "authorization_code",
        }
    )
    response = _request("GET", GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {token['access_token']}"})
    if response.is_error:
        raise GoogleWorkspaceError("Google could not verify the connected account. Please connect again.", 400)
    profile = response.json()
    if not isinstance(profile, dict) or not profile.get("email") or not profile.get("email_verified"):
        raise GoogleWorkspaceError("Google did not provide a verified email address for this account.", 403)
    email = str(profile["email"]).strip().lower()
    domain = (settings.google_allowed_workspace_domain or "").strip().lower().lstrip("@")
    if not domain or email.rsplit("@", 1)[-1] != domain or profile.get("hd") != domain:
        raise GoogleWorkspaceError(f"Connect a verified @{domain} Google Workspace account.", 403)
    return token, email


def get_connection(db: Session) -> GoogleWorkspaceConnection:
    connection = db.scalar(
        select(GoogleWorkspaceConnection).where(GoogleWorkspaceConnection.disconnected_at.is_(None))
    )
    if connection is None:
        raise GoogleWorkspaceError("No Google Workspace account is connected for this college.", 409)
    return connection


def _access_token(connection: GoogleWorkspaceConnection) -> str:
    require_configuration()
    payload = _token_request(
        {
            "client_id": settings.google_oauth_client_id or "",
            "client_secret": settings.google_oauth_client_secret or "",
            "refresh_token": decrypt_refresh_token(connection.refresh_token_ciphertext),
            "grant_type": "refresh_token",
        }
    )
    return str(payload["access_token"])


def google_api_request(
    connection: GoogleWorkspaceConnection,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = _request(
        method,
        url,
        headers={"Authorization": f"Bearer {_access_token(connection)}"},
        params=params,
        json=payload,
    )
    if response.status_code == 401:
        raise GoogleWorkspaceError("The Google connection has expired or been revoked. Reconnect it.", 409)
    if response.is_error:
        message = _error_detail(response, "Google Workspace could not complete this request.")
        if response.status_code == 403:
            message = "Google denied this request. Confirm the account has the requested permissions and reconnect it."
        raise GoogleWorkspaceError(message, 422 if response.status_code < 500 else 502)
    if response.status_code == 204 or not response.content:
        return {}
    result = response.json()
    return result if isinstance(result, dict) else {}


def resource_url(resource_type: str, google_id: str) -> str:
    if resource_type == "form":
        return f"https://docs.google.com/forms/d/{google_id}/edit"
    if resource_type == "spreadsheet":
        return f"https://docs.google.com/spreadsheets/d/{google_id}/edit"
    return f"https://drive.google.com/open?id={google_id}"


def add_resource(
    db: Session,
    *,
    connection: GoogleWorkspaceConnection,
    actor_id: int,
    resource_type: str,
    google_id: str,
    title: str,
) -> GoogleWorkspaceResource:
    resource = GoogleWorkspaceResource(
        connection_id=connection.id,
        created_by_id=actor_id,
        google_resource_id=google_id,
        resource_type=resource_type,
        title=title,
        url=resource_url(resource_type, google_id),
    )
    db.add(resource)
    db.flush()
    return resource


def get_resource(db: Session, resource_id: int, *, resource_type: str | None = None) -> GoogleWorkspaceResource:
    resource = db.get(GoogleWorkspaceResource, resource_id)
    if resource is None or (resource_type is not None and resource.resource_type != resource_type):
        raise GoogleWorkspaceError("Google Workspace resource not found.", 404)
    return resource


def create_form(db: Session, connection: GoogleWorkspaceConnection, *, actor_id: int, title: str, description: str | None) -> GoogleWorkspaceResource:
    created = google_api_request(connection, "POST", f"{FORMS_API}/forms", payload={"info": {"title": title}})
    form_id = str(created.get("formId") or "")
    if not form_id:
        raise GoogleWorkspaceError("Google did not return the new form identifier.", 502)
    if description:
        google_api_request(
            connection,
            "POST",
            f"{FORMS_API}/forms/{form_id}:batchUpdate",
            payload={"requests": [{"updateFormInfo": {"info": {"description": description}, "updateMask": "description"}}]},
        )
    return add_resource(db, connection=connection, actor_id=actor_id, resource_type="form", google_id=form_id, title=title)


def create_spreadsheet(db: Session, connection: GoogleWorkspaceConnection, *, actor_id: int, title: str) -> GoogleWorkspaceResource:
    created = google_api_request(connection, "POST", f"{SHEETS_API}/spreadsheets", payload={"properties": {"title": title}})
    spreadsheet_id = str(created.get("spreadsheetId") or "")
    if not spreadsheet_id:
        raise GoogleWorkspaceError("Google did not return the new spreadsheet identifier.", 502)
    return add_resource(db, connection=connection, actor_id=actor_id, resource_type="spreadsheet", google_id=spreadsheet_id, title=title)


def create_folder(db: Session, connection: GoogleWorkspaceConnection, *, actor_id: int, title: str) -> GoogleWorkspaceResource:
    created = google_api_request(
        connection,
        "POST",
        f"{DRIVE_API}/files",
        payload={"name": title, "mimeType": "application/vnd.google-apps.folder"},
    )
    folder_id = str(created.get("id") or "")
    if not folder_id:
        raise GoogleWorkspaceError("Google did not return the new folder identifier.", 502)
    return add_resource(db, connection=connection, actor_id=actor_id, resource_type="folder", google_id=folder_id, title=title)


def rename_resource(connection: GoogleWorkspaceConnection, resource: GoogleWorkspaceResource, *, title: str) -> None:
    if resource.resource_type == "form":
        google_api_request(
            connection,
            "POST",
            f"{FORMS_API}/forms/{resource.google_resource_id}:batchUpdate",
            payload={"requests": [{"updateFormInfo": {"info": {"title": title}, "updateMask": "title"}}]},
        )
    elif resource.resource_type == "spreadsheet":
        google_api_request(
            connection,
            "POST",
            f"{SHEETS_API}/spreadsheets/{resource.google_resource_id}:batchUpdate",
            payload={"requests": [{"updateSpreadsheetProperties": {"properties": {"title": title}, "fields": "title"}}]},
        )
    else:
        google_api_request(connection, "PATCH", f"{DRIVE_API}/files/{resource.google_resource_id}", payload={"name": title})
    resource.title = title

def has_drive_listing_scope(connection: GoogleWorkspaceConnection) -> bool:
    try:
        granted = set(json.loads(connection.granted_scopes or "[]"))
    except (TypeError, json.JSONDecodeError):
        return False
    return "https://www.googleapis.com/auth/drive.metadata.readonly" in granted


def list_drive_files(
    connection: GoogleWorkspaceConnection,
    *,
    query: str | None = None,
    file_type: str = "all",
    page_token: str | None = None,
    page_size: int = 50,
) -> dict[str, Any]:
    mime_types = {
        "form": "application/vnd.google-apps.form",
        "spreadsheet": "application/vnd.google-apps.spreadsheet",
        "folder": "application/vnd.google-apps.folder",
    }
    if file_type not in {"all", "form", "spreadsheet", "folder", "other"}:
        raise GoogleWorkspaceError("Choose Google Forms, Sheets, folders, or all Drive files.", 422)
    predicates = ["trashed = false"]
    if file_type in mime_types:
        predicates.append(f"mimeType = '{mime_types[file_type]}'")
    elif file_type == "other":
        predicates.append("mimeType != 'application/vnd.google-apps.form'")
        predicates.append("mimeType != 'application/vnd.google-apps.spreadsheet'")
        predicates.append("mimeType != 'application/vnd.google-apps.folder'")
    if query and query.strip():
        escaped = query.strip().replace("\\", "\\\\").replace("'", "\\'")
        predicates.append(f"name contains '{escaped}'")
    params: dict[str, Any] = {
        "q": " and ".join(predicates),
        "pageSize": min(max(page_size, 1), 100),
        "orderBy": "modifiedTime desc",
        "fields": "nextPageToken,files(id,name,mimeType,webViewLink,modifiedTime,iconLink)",
        "includeItemsFromAllDrives": "true",
        "supportsAllDrives": "true",
        "corpora": "allDrives",
    }
    if page_token:
        params["pageToken"] = page_token
    return google_api_request(connection, "GET", f"{DRIVE_API}/files", params=params)


def drive_file_metadata(connection: GoogleWorkspaceConnection, file_id: str) -> dict[str, Any]:
    if not file_id or len(file_id) > 255 or any(char in file_id for char in "/?#"):
        raise GoogleWorkspaceError("That Google Drive file identifier is invalid.", 422)
    return google_api_request(
        connection,
        "GET",
        f"{DRIVE_API}/files/{quote(file_id, safe='')}",
        params={"fields": "id,name,mimeType,webViewLink,modifiedTime,iconLink"},
    )


def form_definition(connection: GoogleWorkspaceConnection, form_id: str) -> dict[str, Any]:
    file = drive_file_metadata(connection, form_id)
    if file.get("mimeType") != "application/vnd.google-apps.form":
        raise GoogleWorkspaceError("That Drive file is not a Google Form.", 422)
    return google_api_request(connection, "GET", f"{FORMS_API}/forms/{quote(form_id, safe='')}")


def form_question_titles(items: list[dict[str, Any]]) -> dict[str, str]:
    titles: dict[str, str] = {}
    for item in items:
        title = str(item.get("title") or "Untitled question")
        question = (item.get("questionItem") or {}).get("question") or {}
        if question.get("questionId"):
            titles[str(question["questionId"])] = title
        for grouped in ((item.get("questionGroupItem") or {}).get("questions") or []):
            if grouped.get("questionId"):
                titles[str(grouped["questionId"])] = title
        titles.update(form_question_titles(item.get("items") or []))
    return titles


def form_responses_for_file(
    connection: GoogleWorkspaceConnection,
    form_id: str,
    *,
    page_size: int = 100,
    page_token: str | None = None,
) -> dict[str, Any]:
    form = form_definition(connection, form_id)
    params: dict[str, Any] = {"pageSize": min(max(page_size, 1), 100)}
    if page_token:
        params["pageToken"] = page_token
    responses = google_api_request(
        connection,
        "GET",
        f"{FORMS_API}/forms/{quote(form_id, safe='')}/responses",
        params=params,
    )
    return {
        **responses,
        "questionTitles": form_question_titles(form.get("items") or []),
        "formTitle": (form.get("info") or {}).get("title") or "Google Form",
    }


def spreadsheet_metadata(connection: GoogleWorkspaceConnection, spreadsheet_id: str) -> dict[str, Any]:
    file = drive_file_metadata(connection, spreadsheet_id)
    if file.get("mimeType") != "application/vnd.google-apps.spreadsheet":
        raise GoogleWorkspaceError("That Drive file is not a Google Sheet.", 422)
    return google_api_request(
        connection,
        "GET",
        f"{SHEETS_API}/spreadsheets/{quote(spreadsheet_id, safe='')}",
        params={"fields": "spreadsheetId,properties(title),sheets(properties(sheetId,title,index,gridProperties(rowCount,columnCount)))"},
    )



def delete_resource(connection: GoogleWorkspaceConnection, resource: GoogleWorkspaceResource) -> None:
    google_api_request(connection, "DELETE", f"{DRIVE_API}/files/{resource.google_resource_id}")


def form_responses(connection: GoogleWorkspaceConnection, resource: GoogleWorkspaceResource) -> dict[str, Any]:
    form_id = resource.google_resource_id if isinstance(resource, GoogleWorkspaceResource) else resource
    return form_responses_for_file(connection, form_id, page_size=100)


def read_spreadsheet_values(connection: GoogleWorkspaceConnection, resource: GoogleWorkspaceResource | str, cell_range: str) -> dict[str, Any]:
    spreadsheet_id = resource.google_resource_id if isinstance(resource, GoogleWorkspaceResource) else resource
    return google_api_request(connection, "GET", f"{SHEETS_API}/spreadsheets/{quote(spreadsheet_id, safe='')}/values/{quote(cell_range, safe='')}")


def write_spreadsheet_values(
    connection: GoogleWorkspaceConnection,
    resource: GoogleWorkspaceResource,
    *,
    cell_range: str,
    values: list[list[Any]],
) -> dict[str, Any]:
    from urllib.parse import quote

    return google_api_request(
        connection,
        "PUT",
        f"{SHEETS_API}/spreadsheets/{resource.google_resource_id}/values/{quote(cell_range, safe='')}",
        params={"valueInputOption": "USER_ENTERED"},
        payload={"values": values},
    )


def revoke_connection(connection: GoogleWorkspaceConnection) -> None:
    try:
        _request(
            "POST",
            "https://oauth2.googleapis.com/revoke",
            data={"token": decrypt_refresh_token(connection.refresh_token_ciphertext)},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    except (GoogleWorkspaceError, httpx.HTTPError):
        # Local disconnect still removes access even if Google's revoke endpoint
        # is temporarily unavailable.
        pass


def scope_list(token: dict[str, Any]) -> str:
    raw = str(token.get("scope") or "")
    # Google may omit `scope` when the requested grant exactly matches the token.
    return json.dumps(sorted(set(raw.split()) if raw else set(SCOPES)))
