from pydantic import BaseModel
from datetime import date
from typing import List, Optional

class StoreBase(BaseModel):
    store_name: str

class StoreCreate(StoreBase):
    pass

class StoreOut(StoreBase):
    id: int
    class Config:
        from_attributes = True

class CampaignBase(BaseModel):
    campaign_name: str
    campaign_type: str
    start_date: date
    end_date: date
    campaign_cost: float

class CampaignCreate(CampaignBase):
    stores: List[str]

class CampaignOut(CampaignBase):
    id: int
    total_customers_targeted: int
    stores: List[StoreOut]
    
    class Config:
        from_attributes = True

class CustomerConversionOut(BaseModel):
    customers_targeted: int
    customers_converted: int
    conversion_rate: float

class CategoryPerformanceOut(BaseModel):
    category: str
    qty_sold: int
    sales_value: float

class DailyTrendOut(BaseModel):
    date: str
    sales_value: float
    qty_sold: int

class StoreKPIsOut(BaseModel):
    store_name: str
    purchase_count: int
    purchase_value: float
    roi: float

class StoreComparisonOut(BaseModel):
    stores: List[StoreKPIsOut]
    conversion_comparisons: List[dict] # store_name, conversion_rate

class Token(BaseModel):
    access_token: str
    token_type: str
