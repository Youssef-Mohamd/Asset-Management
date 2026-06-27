from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from app.models import AssetStatus, AssetType


class AssetCreate(BaseModel):
   
    type: AssetType = Field(..., description="Asset type (domain, subdomain, etc.)")
    value: str = Field(..., min_length=1, max_length=500, description="Canonical asset value")
    status: str = Field(default="active", description="Asset status")
    source: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Where asset came from (scan, import, manual)"
    )
    metadata: Optional[dict] = Field(
        default_factory=dict,
        description="Type-specific metadata (e.g., cert issuer, tech version)"
    )
    tags: Optional[List[str]] = Field(
        default_factory=list,
        description="Free-form labels for filtering and grouping"
    )

    @field_validator("value")
    @classmethod
    def value_must_not_be_empty(cls, v: str) -> str:
        # Ensure value is not just whitespace.
        if not v.strip():
            raise ValueError("Asset value cannot be empty or whitespace")
        return v.strip()

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: Optional[str]) -> Optional[str]:
        # Validate source is one of allowed values.
        if v is None:
            return v
        allowed_sources = ["scan", "import", "manual"]
        if v not in allowed_sources:
            raise ValueError(f"Source must be one of: {', '.join(allowed_sources)}")
        return v

    @field_validator("tags")
    @classmethod
    def tags_must_be_strings(cls, v: List[str]) -> List[str]:
        # Ensure all tags are non-empty strings.
        if not isinstance(v, list):
            raise ValueError("Tags must be a list")
        cleaned = [tag.strip() for tag in v if isinstance(tag, str) and tag.strip()]
        return cleaned

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        # Validate status is one of allowed values.
        allowed_statuses = ["active", "stale", "archived"]
        if v not in allowed_statuses:
            raise ValueError(f"Status must be one of: {', '.join(allowed_statuses)}")
        return v


class AssetUpdate(BaseModel):
  
    status: Optional[str] = Field(
        default=None,
        description="Update asset status"
    )
    source: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Update asset source"
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Update metadata (merged with existing)"
    )
    tags: Optional[List[str]] = Field(
        default=None,
        description="Replace asset tags"
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
       
        if v is None:
            return v
        allowed_statuses = ["active", "stale", "archived"]
        if v not in allowed_statuses:
            raise ValueError(f"Status must be one of: {', '.join(allowed_statuses)}")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
       
        if v is None:
            return v
        if not isinstance(v, list):
            raise ValueError("Tags must be a list")
        cleaned = [tag.strip() for tag in v if isinstance(tag, str) and tag.strip()]
        return cleaned



class AssetResponse(BaseModel):
   
    id: UUID
    type: AssetType
    value: str
    status: AssetStatus
    first_seen: datetime
    last_seen: datetime
    source: Optional[str]
    metadata: Optional[dict] = Field(alias="metadata_")
    tags: List[str] = Field(default_factory=list, alias="tag_names")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class RelationshipCreate(BaseModel):
    # Schema for creating a relationship between assets.
    from_asset_id: UUID = Field(..., description="Source asset ID")
    to_asset_id: UUID = Field(..., description="Target asset ID")
    relation_type: str = Field(..., min_length=1, max_length=100, description="Type of relationship")

    @model_validator(mode="after")
    def check_different_assets(self):
        # Ensure source and target are different.
        if self.from_asset_id == self.to_asset_id:
            raise ValueError("Asset cannot have a relationship to itself")
        return self

    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, v: str) -> str:
        # Validate relation type is not just whitespace.
        if not v.strip():
            raise ValueError("Relation type cannot be empty")
        return v.strip()


class RelationshipResponse(BaseModel):
    # Schema for relationship responses.
    id: UUID
    from_asset_id: UUID
    to_asset_id: UUID
    relation_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BulkImportRequest(BaseModel):  # Schema for bulk import requests.
   
    assets: List[AssetCreate] = Field(
        ...,
        min_items=1,
        max_items=10000,
        description="List of assets to import"
    )


class BulkImportResponse(BaseModel):
    """Schema for bulk import responses."""
    created: int
    updated: int
    duplicates: int
    total: int


class AssetGraphResponse(BaseModel): # Schema for asset graph responses (asset + relationships).
    
    asset: AssetResponse
    relationships: List[RelationshipResponse]
    related_assets: List[AssetResponse]
    relation_count: int


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)