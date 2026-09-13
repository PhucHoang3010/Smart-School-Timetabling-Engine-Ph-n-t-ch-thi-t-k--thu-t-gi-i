from datetime import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from ..core.database import Base

class ScheduleVersionModel(Base):
    __tablename__ = "schedule_versions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), nullable=False, unique=True, index=True)
    parent_version = Column(String(50), nullable=True)
    reason = Column(String(255), nullable=True)
    total_rooms = Column(Integer, default=0)
    total_days = Column(Integer, default=0)
    total_slots = Column(Integer, default=0)
    quality_score = Column(Float, nullable=True)
    teacher_gap = Column(Integer, default=0)
    student_gap = Column(Integer, default=0)
    preference_satisfaction = Column(Float, nullable=True)
    consecutive_overload = Column(Integer, default=0)
    conflict_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class RescheduleEventModel(Base):
    __tablename__ = "reschedule_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_version = Column(String(50), ForeignKey("schedule_versions.version"), nullable=False, index=True)
    target_version = Column(String(50), ForeignKey("schedule_versions.version"), nullable=False, index=True)
    incident_type = Column(String(20), nullable=False)
    affected_id = Column(Integer, nullable=True)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
