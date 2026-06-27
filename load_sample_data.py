#!/usr/bin/env python3
"""
Load sample dataset for testing.

Usage:
  python load_sample_data.py
"""

import json
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal, engine, Base
from app.models import Asset, AssetType, AssetStatus, AssetTag
from datetime import datetime, timezone
import uuid


def load_sample_data():
    """Load sample dataset from sample-data.json."""
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Load JSON
    with open("sample-data.json") as f:
        data = json.load(f)
    
    db = SessionLocal()
    
    try:
        # Clear existing data
        db.query(Asset).delete()
        db.commit()
        
        loaded = 0
        
        for item in data:
            asset = Asset(
                id=uuid.uuid4(),
                type=AssetType[item["type"]],
                value=item["value"],
                status=AssetStatus[item["status"]],
                source=item.get("source", "import"),
                metadata_=item.get("metadata", {}),
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            )
            db.add(asset)
            db.flush()
            
            # Add tags
            for tag in item.get("tags", []):
                tag_obj = AssetTag(asset_id=asset.id, tag=tag)
                db.add(tag_obj)
            
            loaded += 1
        
        db.commit()
        print(f"✓ Loaded {loaded} assets from sample-data.json")
        
        # Show summary
        total = db.query(Asset).count()
        by_type = {}
        for asset_type in AssetType:
            count = db.query(Asset).filter(Asset.type == asset_type).count()
            if count > 0:
                by_type[asset_type.value] = count
        
        print(f"✓ Total assets: {total}")
        print("✓ By type:")
        for asset_type, count in sorted(by_type.items()):
            print(f"  - {asset_type}: {count}")
        
    except Exception as e:
        print(f"✗ Error loading data: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    load_sample_data()
