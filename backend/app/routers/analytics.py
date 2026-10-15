from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timedelta
import pandas as pd
from typing import List
from ..database import get_db
from .. import models, schemas

router = APIRouter()

def categorize_product(item_category: str) -> str:
    if not item_category:
        return "Others"
    cat = item_category.upper()
    if "REFRIGERATOR" in cat: return "Refrigerator"
    if "WASHING MACHINE" in cat: return "Washing Machine"
    if "TV" in cat or "TELEVISION" in cat: return "Television"
    if "AIR CONDITIONER" in cat or "AC" in cat: return "Air Conditioner"
    if "MOBILE" in cat: return "Mobile"
    if "LAPTOP" in cat: return "Laptop"
    return "Others"

@router.get("/{campaign_id}/store/{store_name}/kpi", response_model=schemas.StoreKPIsOut)
def get_store_kpi(campaign_id: int, store_name: str, db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    roi_end_date = campaign.start_date + timedelta(days=2)
    
    # Get campaign customers who purchased at this store during ROI window
    # Join Billing and CampaignCustomer
    purchases = db.query(models.Billing).join(
        models.CampaignCustomer, 
        models.Billing.customer_mobile == models.CampaignCustomer.mobile_number
    ).filter(
        models.CampaignCustomer.campaign_id == campaign_id,
        models.Billing.store_name == store_name,
        models.Billing.date >= campaign.start_date,
        models.Billing.date <= roi_end_date
    ).all()

    purchase_value = sum([p.sold_price for p in purchases])
    purchase_count = len(set([p.customer_mobile for p in purchases]))
    
    # Assume campaign cost is distributed evenly across stores for ROI calc? 
    # Or just use total campaign cost for simple calc as per instructions
    cost = campaign.campaign_cost if campaign.campaign_cost > 0 else 1
    roi = ((purchase_value - cost) / cost) * 100

    return schemas.StoreKPIsOut(
        store_name=store_name,
        purchase_count=purchase_count,
        purchase_value=purchase_value,
        roi=roi
    )

@router.get("/{campaign_id}/store/{store_name}/products", response_model=List[schemas.CategoryPerformanceOut])
def get_store_products(campaign_id: int, store_name: str, db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Product Analysis Window: Start Date to End Date, ALL customers
    purchases = db.query(models.Billing).filter(
        models.Billing.store_name == store_name,
        models.Billing.date >= campaign.start_date,
        models.Billing.date <= campaign.end_date
    ).all()

    categories = {}
    for p in purchases:
        cat_name = categorize_product(p.item_category)
        if cat_name not in categories:
            categories[cat_name] = {"qty": 0, "sales": 0.0}
        categories[cat_name]["qty"] += p.quantity
        categories[cat_name]["sales"] += p.sold_price

    result = []
    for k, v in categories.items():
        result.append(schemas.CategoryPerformanceOut(category=k, qty_sold=v["qty"], sales_value=v["sales"]))
    return result

@router.get("/{campaign_id}/store/{store_name}/trend", response_model=List[schemas.DailyTrendOut])
def get_store_trend(campaign_id: int, store_name: str, db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    
    purchases = db.query(
        models.Billing.date,
        func.sum(models.Billing.sold_price).label('sales'),
        func.sum(models.Billing.quantity).label('qty')
    ).filter(
        models.Billing.store_name == store_name,
        models.Billing.date >= campaign.start_date,
        models.Billing.date <= campaign.end_date
    ).group_by(models.Billing.date).all()
    
    result = []
    for p in purchases:
        result.append(schemas.DailyTrendOut(date=str(p.date), sales_value=float(p.sales), qty_sold=int(p.qty)))
    return result

@router.get("/{campaign_id}/comparison")
def compare_stores(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    
    stores = db.query(models.CampaignStore).filter(models.CampaignStore.campaign_id == campaign_id).all()
    
    results = []
    roi_end_date = campaign.start_date + timedelta(days=2)
    
    for s in stores:
        purchases = db.query(models.Billing).join(
            models.CampaignCustomer, 
            models.Billing.customer_mobile == models.CampaignCustomer.mobile_number
        ).filter(
            models.CampaignCustomer.campaign_id == campaign_id,
            models.Billing.store_name == s.store_name,
            models.Billing.date >= campaign.start_date,
            models.Billing.date <= roi_end_date
        ).all()

        purchase_value = sum([p.sold_price for p in purchases])
        purchase_count = len(set([p.customer_mobile for p in purchases]))
        cost = campaign.campaign_cost if campaign.campaign_cost > 0 else 1
        roi = ((purchase_value - cost) / cost) * 100
        
        # simplified targeted logic: we don't have per-store target count easily, 
        # so we will return store performance metrics
        results.append({
            "store_name": s.store_name,
            "purchase_count": purchase_count,
            "purchase_value": purchase_value,
            "roi": roi
        })
        
    return results
