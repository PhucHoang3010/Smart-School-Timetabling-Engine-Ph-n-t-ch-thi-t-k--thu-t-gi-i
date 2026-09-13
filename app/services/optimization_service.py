import json
from typing import Dict, List, Optional, Set, Tuple
from ..ai_engine.preference_recommender import AIPreferenceRecommender
from ..core.database import Base, SessionLocal, engine_db
from ..models import *
from ..schemas.optimization_schema import *
from ..solver.cpsat_engine import SmartTimetablingEngine
from ..solver.evaluator import TimetableEvaluator
from ..validators.domain_validator import TimetableValidator

Base.metadata.create_all(bind=engine_db)

class DatabaseService:
    @staticmethod
    def save_timetable(version: str, assignments: list, parent_version: Optional[str] = None, reason: Optional[str] = None, total_rooms: int = 0, total_days: int = 0, total_slots: int = 0):
        db = SessionLocal()
        try:
            db.query(ScheduleModel).filter(ScheduleModel.version == version).delete()
            db.query(ScheduleVersionModel).filter(ScheduleVersionModel.version == version).delete()
            db.add(ScheduleVersionModel(version=version, parent_version=parent_version, reason=reason, total_rooms=total_rooms, total_days=total_days, total_slots=total_slots))
            db.add_all([ScheduleModel(version=version, section_id=item.section_id, room_id=item.room_id, day=item.day, slot=item.slot) for item in assignments]); db.commit()
        except Exception:
            db.rollback(); raise
        finally: db.close()
    @staticmethod
    def load_timetable(version: str) -> List[TimetableAssignment]:
        db = SessionLocal()
        try: return [TimetableAssignment(section_id=item.section_id, room_id=item.room_id, day=item.day, slot=item.slot) for item in db.query(ScheduleModel).filter(ScheduleModel.version == version).all()]
        finally: db.close()
    @staticmethod
    def next_reschedule_version(source: str) -> str:
        db = SessionLocal(); base = f"{source}_RESCHEDULED"; candidate = base; suffix = 2
        try:
            while db.query(ScheduleVersionModel).filter(ScheduleVersionModel.version == candidate).first(): candidate = f"{base}_V{suffix}"; suffix += 1
            return candidate
        finally: db.close()
    @staticmethod
    def save_evaluation(version: str, evaluation: EvaluationResult, conflicts: int):
        db = SessionLocal()
        try:
            item = db.query(ScheduleVersionModel).filter(ScheduleVersionModel.version == version).first()
            if item:
                item.quality_score = evaluation.score; item.teacher_gap = evaluation.total_teacher_gaps; item.student_gap = evaluation.total_student_gaps; item.preference_satisfaction = evaluation.quality_details.get("preference_score", 0) / 100; item.consecutive_overload = evaluation.consecutive_violations; item.conflict_count = conflicts; db.commit()
        finally: db.close()

def _preference_scores(teachers: List[Teacher]) -> Dict[Tuple[int, int, int], int]:
    db = SessionLocal(); recommender = AIPreferenceRecommender(db)
    try: return {(teacher.id, day, slot): score for teacher in teachers for (day, slot), score in recommender.teacher_preference_scores(teacher.id).items()}
    finally: db.close()

def validate_request(payload: TimetableRequest):
    TimetableValidator.validate(payload.teachers, payload.rooms, payload.student_classes, payload.sections, payload.days, payload.slots)

def generate(payload: TimetableRequest, save_version: Optional[str] = None):
    validate_request(payload)
    engine = SmartTimetablingEngine(payload.teachers, payload.rooms, payload.student_classes, payload.sections, days=payload.days, slots=payload.slots, preference_scores=_preference_scores(payload.teachers), max_consecutive_slots=payload.max_consecutive_slots)
    assignments, report = engine.solve()
    if not assignments: raise ValueError("Infeasible: Không thể xếp lịch.")
    conflicts, evaluation = TimetableEvaluator.evaluate(assignments, payload.sections, payload.teachers, payload.student_classes, report, max_consecutive_slots=payload.max_consecutive_slots, rooms=payload.rooms)
    if save_version:
        DatabaseService.save_timetable(save_version, assignments, reason="generated", total_rooms=len(payload.rooms), total_days=len(payload.days), total_slots=len(payload.slots)); DatabaseService.save_evaluation(save_version, evaluation, len(conflicts))
    return TimetableResponse(assignments=assignments, evaluation=evaluation, conflicts=conflicts)

def reschedule(payload: TimetableRequest, incident: RescheduleRequest):
    validate_request(payload); original = DatabaseService.load_timetable(incident.version)
    if not original: raise LookupError(f"Không tìm thấy phiên bản lịch '{incident.version}'.")
    blocked = [("teacher", incident.affected_teacher_id, day, slot) for day, slot in incident.unavailable_slots if incident.affected_teacher_id] + [("room", incident.affected_room_id, day, slot) for day, slot in incident.unavailable_slots if incident.affected_room_id]
    engine = SmartTimetablingEngine(payload.teachers, payload.rooms, payload.student_classes, payload.sections, days=payload.days, slots=payload.slots, preference_scores=_preference_scores(payload.teachers), max_consecutive_slots=payload.max_consecutive_slots)
    assignments, report = engine.solve(original_assignments=original, incident_slots=blocked)
    if not assignments: raise ValueError("Không thể điều chỉnh lịch tự động cho sự cố này.")
    target = DatabaseService.next_reschedule_version(incident.version); DatabaseService.save_timetable(target, assignments, parent_version=incident.version, reason=incident.reason or "incident", total_rooms=len(payload.rooms), total_days=len(payload.days), total_slots=len(payload.slots))
    db = SessionLocal(); db.add(RescheduleEventModel(source_version=incident.version, target_version=target, incident_type="teacher" if incident.affected_teacher_id else "room", affected_id=incident.affected_teacher_id or incident.affected_room_id, reason=incident.reason)); db.commit(); db.close()
    conflicts, evaluation = TimetableEvaluator.evaluate(assignments, payload.sections, payload.teachers, payload.student_classes, report, max_consecutive_slots=payload.max_consecutive_slots, rooms=payload.rooms); DatabaseService.save_evaluation(target, evaluation, len(conflicts))
    return TimetableResponse(assignments=assignments, evaluation=evaluation, conflicts=conflicts)
