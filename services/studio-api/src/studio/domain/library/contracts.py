"""Shared validated JSON contracts for REST, notebook tools and memory."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Contract(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", allow_inf_nan=False
    )


class Ingredient(Contract):
    name: str = Field(max_length=300)
    amount: str | float = ""
    unit: str = Field(default="", max_length=100)


class PageContent(Contract):
    markdown: str = Field(default="", max_length=500_000)
    ingredients: list[Ingredient] = Field(default_factory=list, max_length=500)
    steps: list[str] = Field(default_factory=list, max_length=500)
    latex: str = Field(default="", max_length=20_000)
    smiles: str = Field(default="", max_length=10_000)
    variables: dict[str, str | float] = Field(default_factory=dict, max_length=100)


class Citation(Contract):
    source_id: str | None = None
    artifact_id: str | None = None
    url: str | None = Field(default=None, max_length=6000)
    title: str | None = Field(default=None, max_length=500)
    locator: dict[str, Any] = Field(default_factory=dict)
    archive_status: str | None = None


class SourceRef(Contract):
    kind: Literal["page", "source"]
    id: str
    revision: int | None = Field(default=None, ge=1)


class CreateFolder(Contract):
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None


class UpdateFolder(Contract):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: str | None = None
    expected_revision: int = Field(ge=1)


class CreateNotebook(Contract):
    title: str = Field(min_length=1, max_length=300)
    folder_id: str | None = None


class UpdateNotebook(Contract):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    folder_id: str | None = None
    ai_enabled: bool | None = None
    training_enabled: bool | None = None
    expected_revision: int = Field(ge=1)


class CreatePage(Contract):
    notebook_id: str
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["note", "recipe", "formula", "smiles"] = "note"
    content: PageContent = Field(default_factory=PageContent)
    citations: list[Citation] = Field(default_factory=list, max_length=100)


class UpdatePage(Contract):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: PageContent | None = None
    citations: list[Citation] | None = Field(default=None, max_length=100)
    expected_revision: int = Field(ge=1)


class CreateMemory(Contract):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=100_000)
    source_refs: list[SourceRef] = Field(min_length=1, max_length=100)
    generator: str = Field(default="user", max_length=160)


class FetchSource(Contract):
    url: str = Field(min_length=1, max_length=6000)
    title: str | None = Field(default=None, max_length=500)
    citation: dict[str, Any] = Field(default_factory=dict)
    force_refresh: bool = False


class ArchiveArtifact(Contract):
    artifact_id: str


class RestorePage(Contract):
    expected_revision: int = Field(ge=1)
