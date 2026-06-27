
"""
Core business logic for Asset Management system.
"""

from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Optional, Tuple, List
import hashlib
import secrets

from app.config import settings
from app.models import Asset, AssetStatus, AssetTag, Relationship, ApiKey
from app.schemas import AssetCreate, AssetUpdate, RelationshipCreate


#  HELPERS 


def _set_tags(db: Session, asset: Asset, tags: List[str]) -> None:
    """Set tags for an asset, replacing existing ones."""
    # Delete existing tags
    db.query(AssetTag).filter(AssetTag.asset_id == asset.id).delete()
    
    # Add new tags
    for tag_name in tags:
        if tag_name.strip():  # Skip empty tags
            tag = AssetTag(asset_id=asset.id, tag=tag_name.strip())
            db.add(tag)


def _asset_exists(db: Session, asset_id: UUID) -> bool:
    """Check if an asset exists in the database."""
    return db.query(Asset).filter(Asset.id == asset_id).first() is not None


#  ASSETS CRUD 


def get_asset(db: Session, asset_id: UUID) -> Optional[Asset]:
    """Get a single asset by ID."""
    return db.query(Asset).filter(Asset.id == asset_id).first()


def get_assets(
    db: Session,
    type: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[Asset], int]:
   
    query = db.query(Asset)

    # Apply filters
    if type:
        query = query.filter(Asset.type == type)
    if status:
        query = query.filter(Asset.status == status)
    if source:
        query = query.filter(Asset.source == source)
    if tag:
        query = query.join(AssetTag).filter(AssetTag.tag == tag)
    if search:
        query = query.filter(Asset.value.ilike(f"%{search}%"))

    # Count total before pagination
    total = query.count()

    # Apply sorting
    if sort_by == "last_seen":
        sort_column = Asset.last_seen
    elif sort_by == "value":
        sort_column = Asset.value
    else:
        sort_column = Asset.created_at

    if sort_order.lower() == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Apply pagination
    assets = query.offset(skip).limit(limit).all()
    return assets, total


def create_asset(db: Session, data: AssetCreate) -> Asset:
    """Create a new asset."""
    asset = Asset(
        type=data.type,
        value=data.value,
        status=data.status,
        source=data.source,
        metadata_=data.metadata or {},
    )
    db.add(asset)
    db.flush()
    
    # Add tags
    _set_tags(db, asset, data.tags or [])
    
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(db: Session, asset_id: UUID, data: AssetUpdate) -> Optional[Asset]:
    """Update an existing asset."""
    asset = get_asset(db, asset_id)
    if not asset:
        return None

    if data.status is not None:
        asset.status = data.status
    if data.source is not None:
        asset.source = data.source
    if data.metadata is not None:
        asset.metadata_ = data.metadata
    if data.tags is not None:
        _set_tags(db, asset, data.tags)

    asset.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset(db: Session, asset_id: UUID) -> bool:
    """Delete an asset by ID."""
    asset = get_asset(db, asset_id)
    if not asset:
        return False
    db.delete(asset)
    db.commit()
    return True


#  DEDUPLICATION & BULK IMPORT


def upsert_asset(db: Session, data: AssetCreate) -> Tuple[Asset, bool]:
    """
    Create or update an asset (upsert).
    Used for bulk import with deduplication.
    
    Returns:
        Tuple of (asset, is_new) where is_new=True if created, False if updated
    """
    existing = db.query(Asset).filter(
        Asset.type == data.type,
        Asset.value == data.value
    ).first()

    if existing:
        # Update last_seen on re-sighting
        existing.last_seen = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)

        # Merge source if provided
        if data.source:
            existing.source = data.source

        # Merge metadata
        if data.metadata:
            if existing.metadata_ is None:
                existing.metadata_ = {}
            existing.metadata_.update(data.metadata)

        # Merge tags
        if data.tags:
            _set_tags(db, existing, data.tags)

        db.commit()
        db.refresh(existing)
        return existing, False  # Updated

    return create_asset(db, data), True  # Created


def bulk_import(db: Session, assets: List[AssetCreate]) -> dict:
    """Bulk import assets with deduplication."""
    created = 0
    updated = 0

    # Remove duplicates within the batch
    unique_assets = []
    seen = set()

    for asset in assets:
        key = (asset.type, asset.value)

        if key not in seen:
            seen.add(key)
            unique_assets.append(asset)

    duplicates = len(assets) - len(unique_assets)

    # Create or update each asset
    for asset in unique_assets:
        _, is_new = upsert_asset(db, asset)
        if is_new:
            created += 1
        else:
            updated += 1

    return {
        "created": created,
        "updated": updated,
        "duplicates": duplicates,
        "total": len(assets)
    }


#  LIFECYCLE MANAGEMENT 


def mark_stale_assets(db: Session, days: int = 30) -> int:
    """Mark assets as stale if not seen in N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    updated = db.query(Asset).filter(
        Asset.last_seen < cutoff,
        Asset.status == AssetStatus.active
    ).update({"status": AssetStatus.stale})
    db.commit()
    return updated


def activate_asset(db: Session, asset_id: UUID) -> Optional[Asset]:
    """Activate a stale or archived asset."""
    asset = get_asset(db, asset_id)
    if not asset:
        return None
    
    asset.status = AssetStatus.active
    asset.last_seen = datetime.now(timezone.utc)
    asset.updated_at = datetime.now(timezone.utc)
    db.commit()
  try:
        db.refresh(asset)
    except Exception:
        pass
    return asset


#  RELATIONSHIPS 


def create_relationship(db: Session, data: RelationshipCreate) -> Relationship:
    """Create a relationship between two assets."""
    # Validate asset IDs are different
    if data.from_asset_id == data.to_asset_id:
        raise ValueError("Asset cannot have a relationship to itself")

    # Validate both assets exist
    if not _asset_exists(db, data.from_asset_id):
        raise ValueError(f"Source asset {data.from_asset_id} not found")
    if not _asset_exists(db, data.to_asset_id):
        raise ValueError(f"Target asset {data.to_asset_id} not found")

    # Check for duplicate relationship
    existing = db.query(Relationship).filter(
        Relationship.from_asset_id == data.from_asset_id,
        Relationship.to_asset_id == data.to_asset_id,
        Relationship.relation_type == data.relation_type
    ).first()

    if existing:
        raise ValueError("This relationship already exists")

    rel = Relationship(
        from_asset_id=data.from_asset_id,
        to_asset_id=data.to_asset_id,
        relation_type=data.relation_type,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


def get_relationships(db: Session, asset_id: UUID) -> List[Relationship]:
    """Get all relationships for an asset (both incoming and outgoing)."""
    return db.query(Relationship).filter(
        or_(
            Relationship.from_asset_id == asset_id,
            Relationship.to_asset_id == asset_id,
        )
    ).all()


def get_asset_graph(db: Session, asset_id: UUID) -> Optional[dict]:
    """Get an asset with all its related assets (the graph around it)."""
    asset = get_asset(db, asset_id)
    if not asset:
        return None

    relationships = get_relationships(db, asset_id)
    
    # Collect all related asset IDs
    related_ids = set()
    for rel in relationships:
        if rel.from_asset_id == asset_id:
            related_ids.add(rel.to_asset_id)
        else:
            related_ids.add(rel.from_asset_id)

    # Fetch related assets
    related_assets = []
    if related_ids:
        related_assets = db.query(Asset).filter(Asset.id.in_(related_ids)).all()

    return {
        "asset": asset,
        "relationships": relationships,
        "related_assets": related_assets,
        "relation_count": len(relationships)
    }


#  AUTHENTICATION 


def hash_api_key(key: str) -> str:
    """Hash an API key using SHA256."""
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(db: Session, api_key: str) -> bool:
    """Verify if an API key is valid and active."""
    if api_key == settings.API_KEY:
        return True

    key_hash = hash_api_key(api_key)
    db_key = db.query(ApiKey).filter(
        ApiKey.key_hash == key_hash,
        ApiKey.is_active == True
    ).first()
    return db_key is not None


def create_api_key(db: Session, label: Optional[str] = None) -> Tuple[str, str]:
    """Create a new API key. Returns (raw_key, hashed_key)."""
    raw_key = secrets.token_urlsafe(32)
    hashed_key = hash_api_key(raw_key)
    
    api_key = ApiKey(
        key_hash=hashed_key,
        label=label,
        is_active=True
    )
    db.add(api_key)
    db.commit()
    
    return raw_key, hashed_key
