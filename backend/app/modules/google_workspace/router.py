from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import DbSession, require_role
from app.core.tenancy import set_college_scope
from app.modules.identity.models import User
from app.modules.operations.service import log_audit

from . import service
from .models import GoogleWorkspaceConnection, GoogleWorkspaceResource
from .schemas import (
    AuthorizationRead,
    DriveFileListRead,
    DriveFileRead,
    FolderCreateWrite,
    FormCreateWrite,
    FormResponsesRead,
    GoogleFormRead,
    GoogleFormResponsesRead,
    GoogleSpreadsheetRead,
    GoogleWorkspaceResourceRead,
    GoogleWorkspaceStatusRead,
    ResourceTitleWrite,
    SpreadsheetCreateWrite,
    SpreadsheetValuesRead,
    SpreadsheetValuesWrite,
)

router = APIRouter(prefix="/google-workspace", tags=["google-workspace"])
Admin = Annotated[User, Depends(require_role("admin"))]


def error_from(exc: service.GoogleWorkspaceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def resource_read(resource: GoogleWorkspaceResource) -> GoogleWorkspaceResourceRead:
    return GoogleWorkspaceResourceRead(
        id=resource.id,
        resource_type=resource.resource_type,
        title=resource.title,
        url=resource.url,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )


def callback_redirect(result: str) -> RedirectResponse:
    query = urlencode({"google": result})
    return RedirectResponse(f"{settings.frontend_url.rstrip('/')}/admin/google-workspace?{query}", status_code=303)


@router.get("/status", response_model=GoogleWorkspaceStatusRead)
def status(actor: Admin, db: DbSession):
    connection = db.scalar(select(GoogleWorkspaceConnection).where(GoogleWorkspaceConnection.disconnected_at.is_(None)))
    return GoogleWorkspaceStatusRead(
        configured=service.configured(),
        connected=connection is not None,
        google_email=connection.google_email if connection else None,
        connected_at=connection.connected_at if connection else None,
        allowed_workspace_domain=settings.google_allowed_workspace_domain,
        drive_listing_ready=service.has_drive_listing_scope(connection) if connection else False,
    )


@router.get("/authorize", response_model=AuthorizationRead)
def begin_authorization(actor: Admin, db: DbSession):
    if actor.active_college_id is None:
        raise HTTPException(400, "Select a college before connecting Google Workspace.")
    try:
        state = service.create_oauth_attempt(db, user_id=actor.id, college_id=actor.active_college_id)
        db.commit()
        return AuthorizationRead(authorization_url=service.authorization_url(state))
    except service.GoogleWorkspaceError as exc:
        db.rollback()
        raise error_from(exc) from exc


@router.get("/callback", include_in_schema=False)
def authorization_callback(
    db: DbSession,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
):
    try:
        attempt = service.consume_oauth_attempt(db, state)
    except service.GoogleWorkspaceError:
        return callback_redirect("failed")
    if error or not code:
        return callback_redirect("cancelled" if error == "access_denied" else "failed")
    try:
        token, email = service.exchange_code(code)
        set_college_scope(db, attempt.college_id)
        db.info["actor_id"] = attempt.user_id
        connection = db.scalar(select(GoogleWorkspaceConnection))
        refresh_token = token.get("refresh_token")
        if not refresh_token:
            if connection is None or connection.google_email != email:
                raise service.GoogleWorkspaceError(
                    "Google did not return a refresh token. Remove this app from the Google account and connect again.",
                    409,
                )
            ciphertext = connection.refresh_token_ciphertext
        else:
            ciphertext = service.encrypt_refresh_token(str(refresh_token))
        if connection is None:
            connection = GoogleWorkspaceConnection(
                college_id=attempt.college_id,
                connected_by_id=attempt.user_id,
                google_email=email,
                refresh_token_ciphertext=ciphertext,
                granted_scopes=service.scope_list(token),
            )
            db.add(connection)
        else:
            connection.connected_by_id = attempt.user_id
            connection.google_email = email
            connection.refresh_token_ciphertext = ciphertext
            connection.granted_scopes = service.scope_list(token)
            connection.disconnected_at = None
        db.flush()
        log_audit(
            db,
            actor_id=attempt.user_id,
            action="google_workspace.connected",
            entity_type="google_workspace_connections",
            entity_id=connection.id,
            after={"google_email": email, "college_id": attempt.college_id},
            college_id=attempt.college_id,
        )
        db.commit()
    except service.GoogleWorkspaceError:
        db.rollback()
        return callback_redirect("failed")
    return callback_redirect("connected")


@router.delete("/connection", status_code=204)
def disconnect(actor: Admin, db: DbSession):
    try:
        connection = service.get_connection(db)
        service.revoke_connection(connection)
        connection.disconnected_at = datetime.now(timezone.utc)
        log_audit(
            db,
            actor_id=actor.id,
            action="google_workspace.disconnected",
            entity_type="google_workspace_connections",
            entity_id=connection.id,
            before={"google_email": connection.google_email},
            college_id=connection.college_id,
        )
        db.commit()
    except service.GoogleWorkspaceError as exc:
        db.rollback()
        raise error_from(exc) from exc
    return Response(status_code=204)


@router.get("/resources", response_model=list[GoogleWorkspaceResourceRead])
def list_resources(actor: Admin, db: DbSession):
    rows = db.scalars(select(GoogleWorkspaceResource).order_by(GoogleWorkspaceResource.created_at.desc())).all()
    return [resource_read(row) for row in rows]


@router.get("/drive/files", response_model=DriveFileListRead)
def browse_drive_files(
    actor: Admin,
    db: DbSession,
    query: str | None = Query(default=None, max_length=120),
    file_type: str = Query(default="all", alias="type"),
    page_token: str | None = Query(default=None, max_length=5000),
    page_size: int = Query(default=50, ge=1, le=100),
):
    try:
        connection = service.get_connection(db)
        payload = service.list_drive_files(
            connection,
            query=query,
            file_type=file_type,
            page_token=page_token,
            page_size=page_size,
        )
        managed = {
            resource.google_resource_id: resource.id
            for resource in db.scalars(select(GoogleWorkspaceResource)).all()
        }
        files = []
        for item in payload.get("files") or []:
            google_id = str(item.get("id") or "")
            mime_type = str(item.get("mimeType") or "")
            resource_type = (
                "form" if mime_type == "application/vnd.google-apps.form"
                else "spreadsheet" if mime_type == "application/vnd.google-apps.spreadsheet"
                else "folder" if mime_type == "application/vnd.google-apps.folder"
                else "other"
            )
            files.append(DriveFileRead(
                id=google_id,
                name=str(item.get("name") or "Untitled file"),
                mime_type=mime_type,
                url=item.get("webViewLink") or service.resource_url(resource_type, google_id),
                modified_time=item.get("modifiedTime"),
                icon_url=item.get("iconLink"),
                managed_resource_id=managed.get(google_id),
            ))
        return DriveFileListRead(files=files, next_page_token=payload.get("nextPageToken"))
    except service.GoogleWorkspaceError as exc:
        raise error_from(exc) from exc


@router.get("/drive/files/{google_file_id}/form", response_model=GoogleFormRead)
def read_drive_google_form(google_file_id: str, actor: Admin, db: DbSession):
    try:
        connection = service.get_connection(db)
        payload = service.form_definition(connection, google_file_id)
        info = payload.get("info") or {}
        return GoogleFormRead(
            form_id=google_file_id,
            title=str(info.get("title") or "Google Form"),
            description=info.get("description"),
            responder_uri=payload.get("responderUri"),
            items=payload.get("items") or [],
        )
    except service.GoogleWorkspaceError as exc:
        raise error_from(exc) from exc


@router.get("/drive/files/{google_file_id}/responses", response_model=GoogleFormResponsesRead)
def read_drive_google_form_responses(
    google_file_id: str,
    actor: Admin,
    db: DbSession,
    page_size: int = Query(default=50, ge=1, le=100),
    page_token: str | None = Query(default=None, max_length=5000),
):
    try:
        connection = service.get_connection(db)
        payload = service.form_responses_for_file(
            connection, google_file_id, page_size=page_size, page_token=page_token,
        )
        return GoogleFormResponsesRead(
            responses=payload.get("responses") or [],
            question_titles=payload.get("questionTitles") or {},
            next_page_token=payload.get("nextPageToken"),
        )
    except service.GoogleWorkspaceError as exc:
        raise error_from(exc) from exc


@router.get("/drive/files/{google_file_id}/spreadsheet", response_model=GoogleSpreadsheetRead)
def read_drive_google_spreadsheet(google_file_id: str, actor: Admin, db: DbSession):
    try:
        connection = service.get_connection(db)
        payload = service.spreadsheet_metadata(connection, google_file_id)
        return GoogleSpreadsheetRead(

            spreadsheet_id=google_file_id,
            title=str((payload.get("properties") or {}).get("title") or "Google Sheet"),
            sheets=[item.get("properties") or {} for item in payload.get("sheets") or []],
        )
    except service.GoogleWorkspaceError as exc:
        raise error_from(exc) from exc


@router.get("/drive/files/{google_file_id}/values", response_model=SpreadsheetValuesRead)
def read_drive_google_spreadsheet_values(
    google_file_id: str,
    actor: Admin,
    db: DbSession,
    range: str = Query(default="A1:Z100", min_length=1, max_length=500),
):
    try:
        connection = service.get_connection(db)
        service.spreadsheet_metadata(connection, google_file_id)
        payload = service.read_spreadsheet_values(connection, google_file_id, range)
        return SpreadsheetValuesRead(range=payload.get("range"), values=payload.get("values") or [])
    except service.GoogleWorkspaceError as exc:
        raise error_from(exc) from exc

@router.post("/forms", response_model=GoogleWorkspaceResourceRead, status_code=201)
def create_google_form(payload: FormCreateWrite, actor: Admin, db: DbSession):
    try:
        connection = service.get_connection(db)
        resource = service.create_form(
            db,
            connection,
            actor_id=actor.id,
            title=payload.clean_title(),
            description=payload.description.strip() if payload.description else None,
        )
        log_audit(db, actor.id, "google_workspace.form.created", "google_workspace_resources", resource.id,
                  after={"title": resource.title, "resource_type": resource.resource_type}, college_id=resource.college_id)
        db.commit()
        db.refresh(resource)
        return resource_read(resource)
    except service.GoogleWorkspaceError as exc:
        db.rollback()
        raise error_from(exc) from exc


@router.post("/spreadsheets", response_model=GoogleWorkspaceResourceRead, status_code=201)
def create_google_spreadsheet(payload: SpreadsheetCreateWrite, actor: Admin, db: DbSession):
    try:
        connection = service.get_connection(db)
        resource = service.create_spreadsheet(db, connection, actor_id=actor.id, title=payload.clean_title())
        log_audit(db, actor.id, "google_workspace.spreadsheet.created", "google_workspace_resources", resource.id,
                  after={"title": resource.title, "resource_type": resource.resource_type}, college_id=resource.college_id)
        db.commit()
        db.refresh(resource)
        return resource_read(resource)
    except service.GoogleWorkspaceError as exc:
        db.rollback()
        raise error_from(exc) from exc


@router.post("/folders", response_model=GoogleWorkspaceResourceRead, status_code=201)
def create_google_folder(payload: FolderCreateWrite, actor: Admin, db: DbSession):
    try:
        connection = service.get_connection(db)
        resource = service.create_folder(db, connection, actor_id=actor.id, title=payload.clean_title())
        log_audit(db, actor.id, "google_workspace.folder.created", "google_workspace_resources", resource.id,
                  after={"title": resource.title, "resource_type": resource.resource_type}, college_id=resource.college_id)
        db.commit()
        db.refresh(resource)
        return resource_read(resource)
    except service.GoogleWorkspaceError as exc:
        db.rollback()
        raise error_from(exc) from exc


@router.patch("/resources/{resource_id}", response_model=GoogleWorkspaceResourceRead)
def rename_google_resource(resource_id: int, payload: ResourceTitleWrite, actor: Admin, db: DbSession):
    try:
        connection = service.get_connection(db)
        resource = service.get_resource(db, resource_id)
        previous = resource.title
        service.rename_resource(connection, resource, title=payload.clean_title())
        log_audit(db, actor.id, "google_workspace.resource.renamed", "google_workspace_resources", resource.id,
                  before={"title": previous}, after={"title": resource.title}, college_id=resource.college_id)
        db.commit()
        db.refresh(resource)
        return resource_read(resource)
    except service.GoogleWorkspaceError as exc:
        db.rollback()
        raise error_from(exc) from exc


@router.delete("/resources/{resource_id}", status_code=204)
def delete_google_resource(resource_id: int, actor: Admin, db: DbSession):
    try:
        connection = service.get_connection(db)
        resource = service.get_resource(db, resource_id)
        before = {"title": resource.title, "resource_type": resource.resource_type}
        service.delete_resource(connection, resource)
        log_audit(db, actor.id, "google_workspace.resource.deleted", "google_workspace_resources", resource.id,
                  before=before, college_id=resource.college_id)
        db.delete(resource)
        db.commit()
    except service.GoogleWorkspaceError as exc:
        db.rollback()
        raise error_from(exc) from exc
    return Response(status_code=204)


@router.get("/forms/{resource_id}/responses", response_model=FormResponsesRead)
def read_google_form_responses(resource_id: int, actor: Admin, db: DbSession):
    try:
        connection = service.get_connection(db)
        resource = service.get_resource(db, resource_id, resource_type="form")
        payload = service.form_responses(connection, resource)
        return FormResponsesRead(
            responses=payload.get("responses", []),
            next_page_token=payload.get("nextPageToken"),
        )
    except service.GoogleWorkspaceError as exc:
        raise error_from(exc) from exc


@router.get("/spreadsheets/{resource_id}/values", response_model=SpreadsheetValuesRead)
def read_google_spreadsheet_values(
    resource_id: int,
    actor: Admin,
    db: DbSession,
    range: str = Query(default="Sheet1!A1:Z100", min_length=1, max_length=500),
):
    try:
        connection = service.get_connection(db)
        resource = service.get_resource(db, resource_id, resource_type="spreadsheet")
        payload = service.read_spreadsheet_values(connection, resource, range)
        return SpreadsheetValuesRead(range=payload.get("range"), values=payload.get("values", []))
    except service.GoogleWorkspaceError as exc:
        raise error_from(exc) from exc


@router.put("/spreadsheets/{resource_id}/values", response_model=SpreadsheetValuesRead)
def write_google_spreadsheet_values(resource_id: int, payload: SpreadsheetValuesWrite, actor: Admin, db: DbSession):
    try:
        connection = service.get_connection(db)
        resource = service.get_resource(db, resource_id, resource_type="spreadsheet")
        updated = service.write_spreadsheet_values(connection, resource, cell_range=payload.range, values=payload.values)
        log_audit(db, actor.id, "google_workspace.spreadsheet.values_updated", "google_workspace_resources", resource.id,
                  after={"range": payload.range, "updated_cells": updated.get("updatedCells")}, college_id=resource.college_id)
        db.commit()
        return SpreadsheetValuesRead(range=updated.get("updatedRange"), values=updated.get("updatedData", {}).get("values", payload.values))
    except service.GoogleWorkspaceError as exc:
        db.rollback()
        raise error_from(exc) from exc
