"""Shared schema building blocks."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for anything read straight off a SQLAlchemy row."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int | None = Field(
        default=None,
        description="Total matching rows; omitted when counting would be costly.",
    )
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        if self.total is None:
            return len(self.items) >= self.limit
        return self.offset + len(self.items) < self.total


class Pagination(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Message(BaseModel):
    detail: str


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None
