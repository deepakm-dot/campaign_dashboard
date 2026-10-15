from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import pandas as pd
from typing import List
from io import BytesIO
from ..database import get_db
from .. import models

router = APIRouter()

@router.post("/campaign-master/")
async def upload_campaign_master(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(('.xlsx', '.csv')):
        raise HTTPException(status_code=400, detail="Invalid file format")

    contents = await file.read()
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))
        
        # Expected columns: Campaign Name, Campaign Type, Campaign Cost, Start Date, End Date, Store Name
        required_cols = ['Campaign Name', 'Campaign Type', 'Campaign Cost', 'Start Date', 'End Date', 'Store Name']
        if not all(col in df.columns for col in required_cols):
            raise HTTPException(status_code=400, detail=f"Missing required columns. Expected: {required_cols}")

        for index, row in df.iterrows():
            campaign_name = str(row['Campaign Name']).strip()
            # Check if campaign exists
            campaign = db.query(models.Campaign).filter(models.Campaign.campaign_name == campaign_name).first()
            if not campaign:
                campaign = models.Campaign(
                    campaign_name=campaign_name,
                    campaign_type=str(row['Campaign Type']).strip(),
                    start_date=pd.to_datetime(row['Start Date']).date(),
                    end_date=pd.to_datetime(row['End Date']).date(),
                    campaign_cost=float(row['Campaign Cost'])
                )
                db.add(campaign)
                db.commit()
                db.refresh(campaign)

            store_name = str(row['Store Name']).strip()
            # Add store if not already linked
            store_link = db.query(models.CampaignStore).filter(
                models.CampaignStore.campaign_id == campaign.id,
                models.CampaignStore.store_name == store_name
            ).first()
            if not store_link:
                new_store = models.CampaignStore(campaign_id=campaign.id, store_name=store_name)
                db.add(new_store)
        
        db.commit()
        return {"message": "Campaign Master data uploaded successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/campaign-customers/")
async def upload_campaign_customers(campaign_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    contents = await file.read()
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))
            
        if 'Mobile Number' not in df.columns:
            raise HTTPException(status_code=400, detail="Missing column: Mobile Number")
            
        new_customers = 0
        for index, row in df.iterrows():
            mobile = str(row['Mobile Number']).strip()
            if mobile and mobile.lower() != 'nan':
                # Check if exists
                exists = db.query(models.CampaignCustomer).filter(
                    models.CampaignCustomer.campaign_id == campaign_id,
                    models.CampaignCustomer.mobile_number == mobile
                ).first()
                if not exists:
                    db.add(models.CampaignCustomer(campaign_id=campaign_id, mobile_number=mobile))
                    new_customers += 1
        
        # Update targeted count
        campaign.total_customers_targeted += new_customers
        db.commit()
        
        return {"message": f"Added {new_customers} new customers to campaign"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/billing-data/")
async def upload_billing_data(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))
            
        required_cols = ['Invoice Number', 'Customer Mobile', 'Store Name', 'Date', 'Item Category', 'Product Name', 'Quantity', 'Sold Price']
        if not all(col in df.columns for col in required_cols):
            raise HTTPException(status_code=400, detail=f"Missing required columns. Expected: {required_cols}")

        batch_size = 1000
        objects = []
        for index, row in df.iterrows():
            try:
                date_val = pd.to_datetime(row['Date']).date()
            except:
                continue # Skip invalid dates
                
            objects.append(models.Billing(
                invoice_number=str(row['Invoice Number']).strip(),
                customer_mobile=str(row['Customer Mobile']).strip(),
                store_name=str(row['Store Name']).strip(),
                date=date_val,
                item_category=str(row['Item Category']).strip(),
                product_name=str(row['Product Name']).strip(),
                quantity=int(pd.to_numeric(row['Quantity'], errors='coerce') or 0),
                sold_price=float(pd.to_numeric(row['Sold Price'], errors='coerce') or 0.0)
            ))
            
            if len(objects) >= batch_size:
                db.bulk_save_objects(objects)
                db.commit()
                objects = []
                
        if objects:
            db.bulk_save_objects(objects)
            db.commit()
            
        return {"message": "Billing data uploaded successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
