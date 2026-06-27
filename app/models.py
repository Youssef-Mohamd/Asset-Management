from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
import enum
from sqlalchemy import Enum 
from .database import Base


class AssetType(str, enum.Enum):
    domain = "domain"
    subdomain = "subdomain"
    ip_address = "ip_address"
    service = "service"
    certificate = "certificate"
    technology = "technology"

class AssetStatus(str, enum.Enum):
    active = "active"
    stale = "stale"
    archived = "archived"


class Asset(Base):
    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(Enum(AssetType), nullable=False)
    value = Column(String, nullable=False)
    status = Column(Enum(AssetStatus), default=AssetStatus.active)
    first_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source = Column(String)
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    tags = relationship("AssetTag", back_populates="asset", cascade="all, delete")

    @property
    def tag_names(self):
        return [tag.tag for tag in self.tags] if self.tags else []

    relationships_from = relationship("Relationship", foreign_keys="Relationship.from_asset_id", back_populates="from_asset")
    relationships_to = relationship("Relationship", foreign_keys="Relationship.to_asset_id", back_populates="to_asset")



class AssetTag(Base):
    __tablename__ = "asset_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    tag = Column(String, nullable=False)

    asset = relationship("Asset", back_populates="tags")



class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    to_asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    relation_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    from_asset = relationship("Asset", foreign_keys=[from_asset_id], back_populates="relationships_from")
    to_asset = relationship("Asset", foreign_keys=[to_asset_id], back_populates="relationships_to")



class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_hash = Column(String, nullable=False)
    label = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))