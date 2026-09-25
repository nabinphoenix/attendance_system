from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AuthorizationRead(BaseModel):
    authorization_url: str


class GoogleWorkspaceStatusRead(BaseModel):
    configured: bool
    connected: bool
    google_email: str | None = None
    connected_at: datetime | None = None
    allowed_workspace_domain: str | None = None
    drive_listing_ready: bool = False


class GoogleWorkspaceResourceRead(BaseModel):
    id: int
    resource_type: Literal["form", "spreadsheet", "folder"]
    title: str
    url: str
    created_at: datetime
    updated_at: datetime | None = None


class ResourceTitleWrite(BaseModel):
    title: str = Field(min_length=1, max_length=250)

    def clean_title(self) -> str:
        return " ".join(self.title.split())


class FormCreateWrite(ResourceTitleWrite):
    description: str | None = Field(default=None, max_length=10_000)


class SpreadsheetCreateWrite(ResourceTitleWrite):
    pass


class FolderCreateWrite(ResourceTitleWrite):
    pass


class SpreadsheetValuesWrite(BaseModel):
    range: str = Field(min_length=1, max_length=500)
    values: list[list[Any]] = Field(min_length=1, max_length=500)


class FormResponsesRead(BaseModel):
    responses: list[dict[str, Any]]
    next_page_token: str | None = None


class SpreadsheetValuesRead(BaseModel):
    range: str | None = None
    values: list[list[Any]] = Field(default_factory=list)


class DriveFileRead(BaseModel):
    id: str
    name: str
    mime_type: str
    url: str | None = None
    modified_time: datetime | str | None = None
    icon_url: str | None = None
    managed_resource_id: int | None = None


class DriveFileListRead(BaseModel):
    files: list[DriveFileRead]
    next_page_token: str | None = None


class GoogleFormRead(BaseModel):
    form_id: str
    title: str
    description: str | None = None
    responder_uri: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)


class GoogleSpreadsheetRead(BaseModel):
    spreadsheet_id: str
    title: str
    sheets: list[dict[str, Any]] = Field(default_factory=list)


class GoogleFormResponsesRead(BaseModel):
    responses: list[dict[str, Any]] = Field(default_factory=list)
    question_titles: dict[str, str] = Field(default_factory=dict)
    next_page_token: str | None = None
