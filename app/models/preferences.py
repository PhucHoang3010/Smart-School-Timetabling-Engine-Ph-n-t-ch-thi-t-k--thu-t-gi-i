from sqlalchemy import Column, Float, Index, Integer, String
from ..core.database import Base

class HistoricalPreferenceModel(Base):
    __tablename__ = "historical_preferences"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(20), nullable=False)
    entity_id = Column(Integer, nullable=False, index=True)
    day = Column(Integer, nullable=False)
    slot = Column(Integer, nullable=False)
    satisfaction_score = Column(Float, default=1.0)
    __table_args__ = (Index("ix_preferences_entity_slot", "entity_type", "entity_id", "day", "slot"),)
