from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from ..models import HistoricalPreferenceModel

class AIPreferenceRecommender:
    """Historical, data-driven preference recommendation; not a complex ML model."""
    def __init__(self, db_session: Session):
        self.db = db_session

    def teacher_preference_scores(self, teacher_id: int) -> Dict[Tuple[int, int], int]:
        rows = self.db.query(HistoricalPreferenceModel).filter(
            HistoricalPreferenceModel.entity_type == "TEACHER",
            HistoricalPreferenceModel.entity_id == teacher_id).all()
        grouped: Dict[Tuple[int, int], List[float]] = {}
        for row in rows:
            grouped.setdefault((row.day, row.slot), []).append(row.satisfaction_score or 0.0)
        return {key: int(round(sum(values) / len(values) * 100)) for key, values in grouped.items()}

    def recommend_teacher_preferences(self, teacher_id: int, threshold: float = 0.75) -> List[Tuple[int, int]]:
        return [key for key, score in self.teacher_preference_scores(teacher_id).items() if score / 100 >= threshold]
