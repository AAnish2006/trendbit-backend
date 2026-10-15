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

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        stat = db.query(SiteStats).filter(SiteStats.key == "total_visitors").first()
        if not stat:
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
