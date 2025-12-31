"""WordPress import schemas."""

from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ConnectionTestRequest(BaseModel):
    """Request schema for WordPress connection test."""

    url: HttpUrl = Field(..., description="WordPress site URL")
    username: str = Field(default="", description="WordPress username")
    password: str = Field(default="", description="Application password")


class ConnectionTestResponse(BaseModel):
    """Response schema for WordPress connection test."""

    success: bool
    message: str
    site_name: str | None = None
    authenticated: bool = False
    errors: list[str] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    """Request schema for import analysis."""

    source_type: str = Field(
        default="wxr", pattern="^(wxr|rest)$", description="Import source type"
    )
    import_media: bool = Field(default=True, description="Import media files")
    download_media: bool = Field(default=True, description="Download media from URL")
    convert_to_webp: bool = Field(default=True, description="Convert images to WebP")
    webp_quality: int = Field(
        default=85, ge=1, le=100, description="WebP quality (1-100)"
    )
    include_drafts: bool = Field(default=False, description="Include draft posts")
    import_comments: bool = Field(default=False, description="Import comments")
    import_menus: bool = Field(default=False, description="Import navigation menus")
    url: str | None = Field(default=None, description="WordPress REST API URL")
    username: str = Field(default="", description="WordPress username")
    password: str = Field(default="", description="Application password")


class ImportAnalysis(BaseModel):
    """Import analysis result."""

    posts: int = 0
    pages: int = 0
    media: int = 0
    categories: int = 0
    tags: int = 0
    authors: int = 0
    comments: int = 0
    menus: int = 0


class ImportAnalysisResponse(BaseModel):
    """Response schema for import analysis."""

    success: bool
    job_id: str | None = None
    analysis: dict[str, Any] | None = None
    error: str | None = None


class StartImportResponse(BaseModel):
    """Response schema for starting import."""

    success: bool
    job_id: str | None = None
    error: str | None = None


class ImportStatusResponse(BaseModel):
    """Response schema for import status."""

    id: str
    status: str
    progress: int = 0
    current_step: str | None = None
    imported_count: int = 0
    total_count: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class CancelImportResponse(BaseModel):
    """Response schema for cancelling import."""

    success: bool
    error: str | None = None


class ErrorResponse(BaseModel):
    """Unified error response schema."""

    success: bool = False
    error: str
    code: str | None = None
    request_id: str | None = None
    details: dict[str, Any] | None = None
