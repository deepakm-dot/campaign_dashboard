from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from .. import models, schemas

router = APIRouter()

@router.get("/", response_model=List[schemas.CampaignOut])
def get_campaigns(db: Session = Depends(get_db)):
    campaigns = db.query(models.Campaign).all()
    return campaigns

@router.get("/{campaign_id}", response_model=schemas.CampaignOut)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign

@router.get("/category/{campaign_type}", response_model=List[schemas.CampaignOut])
def get_campaigns_by_type(campaign_type: str, db: Session = Depends(get_db)):
    campaigns = db.query(models.Campaign).filter(models.Campaign.campaign_type == campaign_type).all()
    return campaigns
