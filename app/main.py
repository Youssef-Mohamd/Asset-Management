# RESTful API for managing internet-facing assets and their relationships.


from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from uuid import UUID
from typing import Optional
from datetime import datetime
import logging

from .database import engine, get_db, Base
from .schemas import (
    AssetCreate, AssetUpdate, AssetResponse,
    RelationshipCreate, RelationshipResponse,
    BulkImportRequest, BulkImportResponse,
    AssetGraphResponse, ErrorResponse
)
from .auth import require_api_key
from . import services

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# Create FastAPI app with documentation
app = FastAPI(
    title="Asset Management API",
    description="Backend for DarkAtlas Attack Surface Monitoring - Asset Management Module",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

#  EXCEPTION HANDLERS  ..> Handle Pydantic validation errors


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=400,
        content={
            "detail": "Request validation failed",
            "error_code": "VALIDATION_ERROR",
            "errors": exc.errors(),
            "timestamp": datetime.utcnow().isoformat()
        }
    )

#Handle business logic errors
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    
    logger.warning(f"Business logic error: {exc}")
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "error_code": "BUSINESS_ERROR",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected errors."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_code": "INTERNAL_ERROR",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


#  HEALTH CHECK 


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


#  ASSETS CRUD


@app.get("/assets", response_model=dict, tags=["Assets"])
def list_assets(
    type: Optional[str] = Query(None, description="Filter by asset type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    search: Optional[str] = Query(None, description="Search in asset value"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort by field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    db: Session = Depends(get_db),
):
   
    skip = (page - 1) * limit
    assets, total = services.get_assets(
        db, type, status, source, tag, search, skip, limit, sort_by, sort_order
    )
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "data": [AssetResponse.model_validate(a) for a in assets]
    }


@app.post("/assets", response_model=AssetResponse, status_code=201, tags=["Assets"])
def create_asset(
    data: AssetCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    
    try:
        return services.create_asset(db, data)
    except IntegrityError as e:
        logger.error(f"Database integrity error: {e}")
        raise HTTPException(status_code=409, detail="Conflict: duplicate asset")
    except Exception as e:
        logger.error(f"Error creating asset: {e}")
        raise HTTPException(status_code=500, detail="Failed to create asset")


@app.get("/assets/{asset_id}", response_model=AssetResponse, tags=["Assets"])
def get_asset(asset_id: UUID, db: Session = Depends(get_db)):
   
    asset = services.get_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    return asset


@app.patch("/assets/{asset_id}", response_model=AssetResponse, tags=["Assets"])
def update_asset(
    asset_id: UUID,
    data: AssetUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
   
    asset = services.update_asset(db, asset_id, data)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    return asset


@app.delete("/assets/{asset_id}", status_code=204, tags=["Assets"])
def delete_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    
    if not services.delete_asset(db, asset_id):
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")


# ASSET LIFECYCLE 


@app.post("/assets/{asset_id}/activate", response_model=AssetResponse, tags=["Assets"])
def activate_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """Reactivate a stale or archived asset."""
    asset = services.activate_asset(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    return asset


@app.post("/assets/mark-stale", tags=["Assets"])
def mark_stale(
    days: int = Query(30, ge=1, le=365, description="Mark assets stale if not seen in N days"),
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
   
    count = services.mark_stale_assets(db, days)
    return {
        "marked_stale": count,
        "threshold_days": days,
        "timestamp": datetime.utcnow().isoformat()
    }


#  BULK IMPORT 
#- Duplicates within the batch are detected and counted 
#   Existing assets in DB are updated (last_seen, metadata, tags merged)
# Idempotent: importing the same dataset twice produces same result

@app.post("/assets/bulk", response_model=BulkImportResponse, status_code=201, tags=["Assets"])
def bulk_import(
    data: BulkImportRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
   
    try:
        result = services.bulk_import(db, data.assets)
        return BulkImportResponse(**result)
    except Exception as e:
        logger.error(f"Bulk import error: {e}")
        raise HTTPException(status_code=400, detail=f"Bulk import failed: {str(e)}")


#  RELATIONSHIPS 


@app.post("/relationships", response_model=RelationshipResponse, status_code=201, tags=["Relationships"])
def create_relationship(
    data: RelationshipCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
 
    try:
        return services.create_relationship(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating relationship: {e}")
        raise HTTPException(status_code=500, detail="Failed to create relationship")


@app.get("/assets/{asset_id}/relationships", response_model=list[RelationshipResponse], tags=["Relationships"])
def get_relationships(asset_id: UUID, db: Session = Depends(get_db)):
    """Get all relationships for an asset (both incoming and outgoing)."""
    # Verify asset exists
    if not services.get_asset(db, asset_id):
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    relationships = services.get_relationships(db, asset_id)
    return relationships


@app.get("/assets/{asset_id}/graph", response_model=AssetGraphResponse, tags=["Relationships"])
def get_asset_graph(asset_id: UUID, db: Session = Depends(get_db)):
   
    graph = services.get_asset_graph(db, asset_id)
    if not graph:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    return AssetGraphResponse(
        asset=graph["asset"],
        relationships=graph["relationships"],
        related_assets=graph["related_assets"],
        relation_count=graph["relation_count"]
    )
