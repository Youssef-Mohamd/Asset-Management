
# Tests core CRUD operations, deduplication, lifecycle, and relationships.


import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from uuid import uuid4
from datetime import datetime, timedelta

from app.database import Base
from app.main import app
from app.database import get_db
from app.models import Asset, AssetType, AssetStatus
from app import services


# ──── DATABASE SETUP ─────────────────────────────────────────────


@pytest.fixture(scope="function")
def db_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for each test."""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """Create a FastAPI test client with mocked database."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


#  FIXTURES 


@pytest.fixture
def sample_domain(db_session):
    """Create a sample domain asset."""
    asset = Asset(
        id=uuid4(),
        type=AssetType.domain,
        value="example.com",
        status=AssetStatus.active,
        source="scan",
        metadata_={}
    )
    db_session.add(asset)
    db_session.commit()
    return asset


@pytest.fixture
def sample_subdomain(db_session, sample_domain):
    """Create a sample subdomain asset."""
    asset = Asset(
        id=uuid4(),
        type=AssetType.subdomain,
        value="api.example.com",
        status=AssetStatus.active,
        source="scan",
        metadata_={}
    )
    db_session.add(asset)
    db_session.commit()
    return asset


#  TESTS: CRUD 


class TestAssetCRUD:
    """Test asset creation, reading, updating, deletion."""

    def test_create_asset(self, db_session):
        """Test creating an asset."""
        from app.schemas import AssetCreate

        asset_data = AssetCreate(
            type=AssetType.domain,
            value="test.com",
            source="manual",
            tags=["test", "prod"]
        )
        asset = services.create_asset(db_session, asset_data)

        assert asset.value == "test.com"
        assert asset.type == AssetType.domain
        assert asset.status == AssetStatus.active
        assert len(asset.tags) == 2

    def test_get_asset(self, db_session, sample_domain):
        """Test retrieving an asset."""
        asset = services.get_asset(db_session, sample_domain.id)

        assert asset is not None
        assert asset.id == sample_domain.id
        assert asset.value == "example.com"

    def test_get_nonexistent_asset(self, db_session):
        """Test retrieving a nonexistent asset."""
        asset = services.get_asset(db_session, uuid4())
        assert asset is None

    def test_update_asset(self, db_session, sample_domain):
        """Test updating an asset."""
        from app.schemas import AssetUpdate

        update_data = AssetUpdate(
            status="stale",
            tags=["updated"]
        )
        updated = services.update_asset(db_session, sample_domain.id, update_data)

        assert updated.status == AssetStatus.stale
        assert len(updated.tags) == 1

    def test_delete_asset(self, db_session, sample_domain):
        """Test deleting an asset."""
        result = services.delete_asset(db_session, sample_domain.id)
        assert result is True

        # Verify it's gone
        asset = services.get_asset(db_session, sample_domain.id)
        assert asset is None

    def test_delete_nonexistent_asset(self, db_session):
        """Test deleting a nonexistent asset."""
        result = services.delete_asset(db_session, uuid4())
        assert result is False


#  TESTS: DEDUPLICATION 


class TestDeduplication:
    """Test deduplication and upsert logic."""

    def test_upsert_new_asset(self, db_session):
        """Test creating a new asset via upsert."""
        from app.schemas import AssetCreate

        asset_data = AssetCreate(
            type=AssetType.domain,
            value="new.com",
            source="scan",
            tags=["initial"]
        )
        asset, is_new = services.upsert_asset(db_session, asset_data)

        assert is_new is True
        assert asset.value == "new.com"

    def test_upsert_existing_asset(self, db_session, sample_domain):
        """Test updating an existing asset via upsert."""
        from app.schemas import AssetCreate

        asset_data = AssetCreate(
            type=AssetType.domain,
            value="example.com",  # Same as sample
            source="scan",
            tags=["updated"]
        )
        asset, is_new = services.upsert_asset(db_session, asset_data)

        assert is_new is False
        assert asset.id == sample_domain.id
        assert asset.last_seen > sample_domain.last_seen

    def test_bulk_import_deduplication(self, db_session):
        """Test deduplication in bulk import."""
        from app.schemas import AssetCreate

        assets = [
            AssetCreate(type=AssetType.domain, value="dup.com", source="scan"),
            AssetCreate(type=AssetType.domain, value="dup.com", source="scan"),  # Duplicate
            AssetCreate(type=AssetType.domain, value="unique.com", source="scan"),
        ]

        result = services.bulk_import(db_session, assets)

        assert result["created"] == 2
        assert result["duplicates"] == 1
        assert result["total"] == 3

    def test_bulk_import_existing_assets(self, db_session, sample_domain):
        """Test bulk import with assets already in DB."""
        from app.schemas import AssetCreate

        assets = [
            AssetCreate(type=AssetType.domain, value="example.com", source="scan"),  # Exists
            AssetCreate(type=AssetType.domain, value="new.com", source="scan"),  # New
        ]

        result = services.bulk_import(db_session, assets)

        assert result["created"] == 1
        assert result["updated"] == 1
        assert result["duplicates"] == 0


#  TESTS: LIFECYCLE 


class TestLifecycle:
    """Test asset lifecycle management."""

    def test_mark_stale_assets(self, db_session, sample_domain):
    
        # Set last_seen to 40 days ago
        old_date = datetime.utcnow() - timedelta(days=40)
        sample_domain.last_seen = old_date
        db_session.commit()

        # Mark stale with 30 day threshold
        count = services.mark_stale_assets(db_session, days=30)

        assert count == 1
        db_session.refresh(sample_domain)
        assert sample_domain.status == AssetStatus.stale

    def test_activate_asset(self, db_session):
        """Test activating a stale asset."""
        asset = Asset(
            type=AssetType.domain,
            value="stale.com",
            status=AssetStatus.stale
        )
        db_session.add(asset)
        db_session.commit()

        activated = services.activate_asset(db_session, asset.id)

        assert activated.status == AssetStatus.active
        assert activated.last_seen > asset.last_seen


#  TESTS: RELATIONSHIPS 


class TestRelationships:
    

    def test_create_relationship(self, db_session, sample_domain, sample_subdomain):
        
        from app.schemas import RelationshipCreate

        rel_data = RelationshipCreate(
            from_asset_id=sample_domain.id,
            to_asset_id=sample_subdomain.id,
            relation_type="parent"
        )
        relationship = services.create_relationship(db_session, rel_data)

        assert relationship.from_asset_id == sample_domain.id
        assert relationship.to_asset_id == sample_subdomain.id
        assert relationship.relation_type == "parent"

    def test_create_self_relationship_fails(self, db_session, sample_domain):
        """Test that self-relationships are rejected."""
        from app.schemas import RelationshipCreate

        rel_data = RelationshipCreate(
            from_asset_id=sample_domain.id,
            to_asset_id=sample_domain.id,
            relation_type="parent"
        )

        with pytest.raises(ValueError):
            services.create_relationship(db_session, rel_data)

    def test_create_relationship_nonexistent_asset(self, db_session, sample_domain):
        
        from app.schemas import RelationshipCreate

        rel_data = RelationshipCreate(
            from_asset_id=sample_domain.id,
            to_asset_id=uuid4(),
            relation_type="parent"
        )

        with pytest.raises(ValueError):
            services.create_relationship(db_session, rel_data)

    def test_get_relationships(self, db_session, sample_domain, sample_subdomain):
       
        from app.schemas import RelationshipCreate

        rel_data = RelationshipCreate(
            from_asset_id=sample_domain.id,
            to_asset_id=sample_subdomain.id,
            relation_type="parent"
        )
        services.create_relationship(db_session, rel_data)

        # Get relationships from domain perspective
        rels = services.get_relationships(db_session, sample_domain.id)
        assert len(rels) == 1
        assert rels[0].relation_type == "parent"

    def test_get_asset_graph(self, db_session, sample_domain, sample_subdomain):
       
        from app.schemas import RelationshipCreate

        # Create relationship
        rel_data = RelationshipCreate(
            from_asset_id=sample_domain.id,
            to_asset_id=sample_subdomain.id,
            relation_type="parent"
        )
        services.create_relationship(db_session, rel_data)

        # Get graph
        graph = services.get_asset_graph(db_session, sample_domain.id)

        assert graph["asset"].id == sample_domain.id
        assert len(graph["relationships"]) == 1
        assert len(graph["related_assets"]) == 1
        assert graph["relation_count"] == 1


#  TESTS: API ENDPOINTS 


class TestAPIEndpoints:
   

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_list_assets(self, client, db_session, sample_domain):
        """Test listing assets."""
        response = client.get("/assets")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["data"]) >= 1

    def test_get_asset(self, client, sample_domain):
        #Test getting a single asset
        response = client.get(f"/assets/{sample_domain.id}")
        assert response.status_code == 200
        assert response.json()["value"] == "example.com"

    def test_get_nonexistent_asset(self, client):
        #Test getting a nonexistent asset.
        response = client.get(f"/assets/{uuid4()}")
        assert response.status_code == 404

    def test_pagination(self, client, db_session):
        
        from app.schemas import AssetCreate

        # Create 5 assets
        for i in range(5):
            asset_data = AssetCreate(
                type=AssetType.domain,
                value=f"asset{i}.com"
            )
            services.create_asset(db_session, asset_data)

        
        response = client.get("/assets?limit=2&page=1")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 2
        assert len(data["data"]) == 2

        # Get second page
        response = client.get("/assets?limit=2&page=2")
        assert len(response.json()["data"]) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
