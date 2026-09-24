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
