import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trendbit.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class SiteStats(Base):
    __tablename__ = "site_stats"

    key = Column(String(64), primary_key=True)
    value = Column(Integer, default=0)

class AppClick(Base):
    __tablename__ = "app_clicks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(64), nullable=True)
    app_id = Column(String(64), nullable=True)
    app_name = Column(String(255), nullable=True)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        stat = db.query(SiteStats).filter(SiteStats.key == "total_visitors").first()
        if not stat:
            # Starts at 0 real visitors (no mock data)
            db.add(SiteStats(key="total_visitors", value=0))
            db.commit()
    finally:
        db.close()

def get_total_visitors() -> int:
    db = SessionLocal()
    try:
        stat = db.query(SiteStats).filter(SiteStats.key == "total_visitors").first()
        return stat.value if stat else 0
    finally:
        db.close()

def increment_total_visitors() -> int:
    db = SessionLocal()
    try:
        stat = db.query(SiteStats).filter(SiteStats.key == "total_visitors").first()
        if not stat:
            stat = SiteStats(key="total_visitors", value=0)
            db.add(stat)
        stat.value += 1
        db.commit()
        return stat.value
    finally:
        db.close()

def record_local_click(
    product_id: str,
    app_id: Optional[str] = None,
    app_name: Optional[str] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> int:
    db = SessionLocal()
    try:
        click_entry = AppClick(
            product_id=str(product_id),
            app_id=str(app_id) if app_id else None,
            app_name=str(app_name) if app_name else None,
            user_agent=str(user_agent) if user_agent else None,
            ip_address=str(ip_address) if ip_address else None,
            created_at=datetime.utcnow()
        )
        db.add(click_entry)
        db.commit()
        total = db.query(AppClick).filter(AppClick.product_id == str(product_id)).count()
        return total
    finally:
        db.close()

def get_total_app_clicks(product_id: str) -> int:
    db = SessionLocal()
    try:
        return db.query(AppClick).filter(AppClick.product_id == str(product_id)).count()
    finally:
        db.close()
