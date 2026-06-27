

from fastapi import HTTPException, Header, Depends
from sqlalchemy.orm import Session

from .database import get_db
from . import services


async def require_api_key(
    x_api_key: str = Header(..., description="API key for authentication"),
    db: Session = Depends(get_db)
) -> None:
   
    if not x_api_key or not x_api_key.strip():
        raise HTTPException(
            status_code=401,
            detail="Missing API key in X-API-Key header"
        )
    
    if not services.verify_api_key(db, x_api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
