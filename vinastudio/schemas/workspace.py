"""Pydantic schemas for workspace management."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceInfo(BaseModel):
    """Response for GET /api/workspace."""

    path: str = Field(..., description="Absolute path to the workspace root")
    name: str = Field(..., description="User-chosen workspace name")
    version: int = Field(..., description="Workspace format version")
    created_at: str = Field(..., alias="createdAt", description="ISO-8601 creation timestamp")
    is_valid: bool = Field(..., alias="isValid", description="True if the config file exists")
    subdirectories: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of subdir name → absolute path",
    )

    model_config = {"populate_by_name": True}


class WorkspaceInitRequest(BaseModel):
    """POST /api/workspace/init — first-launch setup."""

    path: str = Field(..., description="Directory to initialise as workspace")
    name: str = Field(default="VinaStudio Workspace", description="Human-readable name")


class WorkspaceMigrateRequest(BaseModel):
    """POST /api/workspace/migrate — copy workspace to a new location."""

    target_path: str = Field(..., alias="targetPath", description="Destination directory")

    model_config = {"populate_by_name": True}


class WorkspaceSetRequest(BaseModel):
    """POST /api/workspace/set — switch to an existing workspace."""

    path: str = Field(..., description="Path to an existing workspace directory")
