from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    campaign_name = Column(String, index=True)
    campaign_type = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    campaign_cost = Column(Float)
    total_customers_targeted = Column(Integer, default=0)

    stores = relationship("CampaignStore", back_populates="campaign", cascade="all, delete-orphan")
    customers = relationship("CampaignCustomer", back_populates="campaign", cascade="all, delete-orphan")

class CampaignStore(Base):
    __tablename__ = "campaign_stores"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    store_name = Column(String, index=True)

    campaign = relationship("Campaign", back_populates="stores")

class CampaignCustomer(Base):
    __tablename__ = "campaign_customers"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    mobile_number = Column(String, index=True)

    campaign = relationship("Campaign", back_populates="customers")

class Billing(Base):
    __tablename__ = "billing_data"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String, index=True)
    customer_mobile = Column(String, index=True)
    store_name = Column(String, index=True)
    date = Column(Date, index=True)
    item_category = Column(String)
    product_name = Column(String)
    quantity = Column(Integer)
    sold_price = Column(Float)
