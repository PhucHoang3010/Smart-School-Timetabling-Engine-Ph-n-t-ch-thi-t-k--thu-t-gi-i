from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from ..core.database import Base

class ScheduleModel(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), nullable=False, index=True)
    section_id = Column(Integer, ForeignKey("course_sections.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    day = Column(Integer, nullable=False)
    slot = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_schedules_version_slot", "version", "day", "slot"),)
