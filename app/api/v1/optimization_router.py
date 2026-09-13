import json
from typing import Dict, List, Set, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query
from ...core.auth import current_user, require_roles
from ...ai_engine.preference_recommender import AIPreferenceRecommender
from ...core.database import SessionLocal
from ...models import *
from ...schemas.optimization_schema import *
from ...services.optimization_service import DatabaseService, generate, reschedule
from ...validators.domain_validator import DataValidationError

router = APIRouter(prefix="/api/v1")

def _error(error):
    if isinstance(error, DataValidationError): return HTTPException(400, {"message": "Dữ liệu không hợp lệ", "errors": error.errors})
    if isinstance(error, LookupError): return HTTPException(404, str(error))
    return HTTPException(422, str(error))

@router.post("/timetables/generate", response_model=TimetableResponse, tags=["Timetables"], dependencies=[Depends(require_roles("ADMIN"))])
def generate_timetable(payload: TimetableRequest):
    try: return generate(payload)
    except Exception as error: raise _error(error)

@router.post("/timetables/generate-and-save", response_model=TimetableResponse, tags=["Timetables"], dependencies=[Depends(require_roles("ADMIN"))])
def generate_and_save_timetable(payload: TimetableRequest, version: str = Query("HK1_2026_V1")):
    try: return generate(payload, version)
    except Exception as error: raise _error(error)

@router.post("/timetables/auto-reschedule", response_model=TimetableResponse, tags=["Timetables"], dependencies=[Depends(require_roles("ADMIN"))])
def auto_reschedule(payload: TimetableRequest, incident: RescheduleRequest):
    try: return reschedule(payload, incident)
    except Exception as error: raise _error(error)

@router.get("/timetables/versions", response_model=List[Dict], tags=["Timetables"], dependencies=[Depends(require_roles("ADMIN"))])
def list_versions():
    db = SessionLocal()
    try:
        return [{"version": item.version, "parent_version": item.parent_version, "reason": item.reason, "created_at": item.created_at} for item in db.query(ScheduleVersionModel).order_by(ScheduleVersionModel.created_at.desc()).all()]
    finally: db.close()

@router.get("/timetables/compare", response_model=Dict, tags=["Timetables"], dependencies=[Depends(require_roles("ADMIN"))])
def compare_timetables(source_version: str, target_version: str):
    def group(version):
        result = {}
        for item in DatabaseService.load_timetable(version): result.setdefault(item.section_id, set()).add((item.room_id, item.day, item.slot))
        return result
    source, target = group(source_version), group(target_version); changed = [item for item in sorted(set(source) | set(target)) if source.get(item, set()) != target.get(item, set())]
    return {"source_version": source_version, "target_version": target_version, "changed_sections": changed, "changed_count": len(changed), "source_assignments": {key: sorted(value) for key, value in source.items()}, "target_assignments": {key: sorted(value) for key, value in target.items()}}

@router.get("/timetables/{version}", response_model=List[TimetableAssignment], tags=["Timetables"])
def get_version(version: str, user=Depends(current_user)):
    result = DatabaseService.load_timetable(version)
    if not result: raise HTTPException(404, f"Không tìm thấy phiên bản lịch '{version}'.")
    if user.get("role") == "TEACHER":
        db = SessionLocal()
        try:
            section_ids = {item.id for item in db.query(CourseSectionModel).filter(CourseSectionModel.teacher_id == user.get("teacher_id")).all()}
        finally:
            db.close()
        result = [item for item in result if item.section_id in section_ids]
    return result

@router.get("/teachers/me/timetable", response_model=List[TimetableAssignment], tags=["Teachers"])
def teacher_timetable(version: str = Query("HK1_2026_V1"), user=Depends(require_roles("TEACHER"))):
    teacher_id = user.get("teacher_id")
    db = SessionLocal()
    try:
        section_ids = {item.id for item in db.query(CourseSectionModel).filter(CourseSectionModel.teacher_id == teacher_id).all()}
    finally:
        db.close()
    return [item for item in DatabaseService.load_timetable(version) if item.section_id in section_ids]

@router.post("/timetables/{version}/rollback", response_model=List[TimetableAssignment], tags=["Timetables"], dependencies=[Depends(require_roles("ADMIN"))])
def rollback_version(version: str, request: RollbackRequest):
    assignments = DatabaseService.load_timetable(request.target_version)
    if not assignments:
        raise HTTPException(404, f"Không tìm thấy phiên bản lịch '{request.target_version}'.")
    DatabaseService.save_timetable(version, assignments, parent_version=request.target_version, reason="rollback")
    return assignments

@router.delete("/timetables/{version}", tags=["Timetables"], dependencies=[Depends(require_roles("ADMIN"))])
def delete_version(version: str):
    db = SessionLocal()
    try:
        deleted = db.query(ScheduleModel).filter(ScheduleModel.version == version).delete()
        db.query(ScheduleVersionModel).filter(ScheduleVersionModel.version == version).delete(); db.commit()
    finally: db.close()
    if not deleted: raise HTTPException(404, f"Không tìm thấy phiên bản lịch '{version}'.")
    return {"deleted": version}

@router.post("/teachers", response_model=Teacher, status_code=201, tags=["Teachers"], dependencies=[Depends(require_roles("ADMIN"))])
def create_teacher(item: Teacher):
    db = SessionLocal()
    try:
        db.add(TeacherModel(id=item.id, name=item.name, unavailable_slots=json.dumps(item.unavailable_slots), preferred_slots=json.dumps(item.preferred_slots))); db.commit(); return item
    except Exception as error:
        db.rollback(); raise HTTPException(400, f"Không thể tạo teacher: {error}")
    finally: db.close()

@router.get("/teachers", response_model=List[Teacher], tags=["Teachers"], dependencies=[Depends(require_roles("ADMIN"))])
def list_teachers():
    db = SessionLocal()
    try:
        return [Teacher(id=item.id, name=item.name, unavailable_slots=json.loads(item.unavailable_slots or "[]"), preferred_slots=json.loads(item.preferred_slots or "[]")) for item in db.query(TeacherModel).order_by(TeacherModel.id).all()]
    finally: db.close()

@router.put("/teachers/{teacher_id}", response_model=Teacher, tags=["Teachers"], dependencies=[Depends(require_roles("ADMIN"))])
def update_teacher(teacher_id: int, item: Teacher):
    db = SessionLocal()
    try:
        record = db.get(TeacherModel, teacher_id)
        if not record: raise HTTPException(404, "Teacher không tồn tại.")
        record.name = item.name; record.unavailable_slots = json.dumps(item.unavailable_slots); record.preferred_slots = json.dumps(item.preferred_slots); db.commit(); return item
    finally: db.close()

@router.delete("/teachers/{teacher_id}", tags=["Teachers"], dependencies=[Depends(require_roles("ADMIN"))])
def delete_teacher(teacher_id: int):
    db = SessionLocal()
    try:
        record = db.get(TeacherModel, teacher_id)
        if not record: raise HTTPException(404, "Teacher không tồn tại.")
        db.delete(record); db.commit(); return {"deleted": teacher_id}
    finally: db.close()

@router.post("/rooms", response_model=Room, status_code=201, tags=["Rooms"], dependencies=[Depends(require_roles("ADMIN"))])
def create_room(item: Room):
    db = SessionLocal()
    try:
        db.add(RoomModel(id=item.id, name=item.name, capacity=item.capacity, room_type=item.room_type, equipment=json.dumps(item.equipment))); db.commit(); return item
    except Exception as error:
        db.rollback(); raise HTTPException(400, f"Không thể tạo room: {error}")
    finally: db.close()

@router.get("/rooms", response_model=List[Room], tags=["Rooms"], dependencies=[Depends(require_roles("ADMIN"))])
def list_rooms():
    db = SessionLocal()
    try:
        return [Room(id=item.id, name=item.name, capacity=item.capacity, room_type=item.room_type, equipment=json.loads(item.equipment or "[]")) for item in db.query(RoomModel).order_by(RoomModel.id).all()]
    finally: db.close()

@router.put("/rooms/{room_id}", response_model=Room, tags=["Rooms"], dependencies=[Depends(require_roles("ADMIN"))])
def update_room(room_id: int, item: Room):
    db = SessionLocal()
    try:
        record = db.get(RoomModel, room_id)
        if not record: raise HTTPException(404, "Room không tồn tại.")
        record.name = item.name; record.capacity = item.capacity; record.room_type = item.room_type; record.equipment = json.dumps(item.equipment); db.commit(); return item
    finally: db.close()

@router.delete("/rooms/{room_id}", tags=["Rooms"], dependencies=[Depends(require_roles("ADMIN"))])
def delete_room(room_id: int):
    db = SessionLocal()
    try:
        record = db.get(RoomModel, room_id)
        if not record: raise HTTPException(404, "Room không tồn tại.")
        db.delete(record); db.commit(); return {"deleted": room_id}
    finally: db.close()

@router.post("/classes", response_model=StudentClass, status_code=201, tags=["Classes"], dependencies=[Depends(require_roles("ADMIN"))])
def create_class(item: StudentClass):
    db = SessionLocal()
    try:
        db.add(StudentClassModel(id=item.id, name=item.name, size=item.size)); db.commit(); return item
    except Exception as error:
        db.rollback(); raise HTTPException(400, f"Không thể tạo class: {error}")
    finally: db.close()

@router.get("/classes", response_model=List[StudentClass], tags=["Classes"], dependencies=[Depends(require_roles("ADMIN"))])
def list_classes():
    db = SessionLocal()
    try: return [StudentClass(id=item.id, name=item.name, size=item.size) for item in db.query(StudentClassModel).order_by(StudentClassModel.id).all()]
    finally: db.close()

@router.put("/classes/{class_id}", response_model=StudentClass, tags=["Classes"], dependencies=[Depends(require_roles("ADMIN"))])
def update_class(class_id: int, item: StudentClass):
    db = SessionLocal()
    try:
        record = db.get(StudentClassModel, class_id)
        if not record:
            raise HTTPException(404, "Class không tồn tại.")
        record.name, record.size = item.name, item.size
        db.commit()
        return StudentClass(id=class_id, name=record.name, size=record.size)
    finally:
        db.close()

@router.delete("/classes/{class_id}", tags=["Classes"], dependencies=[Depends(require_roles("ADMIN"))])
def delete_class(class_id: int):
    db = SessionLocal()
    try:
        record = db.get(StudentClassModel, class_id)
        if not record:
            raise HTTPException(404, "Class không tồn tại.")
        if db.query(CourseSectionModel).filter(CourseSectionModel.class_id == class_id).first():
            raise HTTPException(409, "Không thể xóa class đang được section sử dụng.")
        db.delete(record); db.commit(); return {"deleted": class_id}
    finally:
        db.close()

@router.post("/sections", response_model=CourseSection, status_code=201, tags=["Sections"], dependencies=[Depends(require_roles("ADMIN"))])
def create_section(item: CourseSection):
    db = SessionLocal()
    try:
        if not db.get(TeacherModel, item.teacher_id) or not db.get(StudentClassModel, item.class_id): raise HTTPException(400, "Teacher hoặc class tham chiếu không tồn tại.")
        db.add(CourseSectionModel(id=item.id, name=item.name, teacher_id=item.teacher_id, class_id=item.class_id, num_slots=item.num_slots, expected_size=item.expected_size, required_room_type=item.required_room_type, required_equipment=json.dumps(item.required_equipment), preferred_days=json.dumps(item.preferred_days))); db.commit(); return item
    except HTTPException: raise
    except Exception as error:
        db.rollback(); raise HTTPException(400, f"Không thể tạo section: {error}")
    finally: db.close()

@router.get("/sections", response_model=List[CourseSection], tags=["Sections"], dependencies=[Depends(require_roles("ADMIN"))])
def list_sections():
    db = SessionLocal()
    try:
        return [CourseSection(id=item.id, name=item.name, teacher_id=item.teacher_id, class_id=item.class_id, num_slots=item.num_slots, expected_size=item.expected_size, required_room_type=item.required_room_type, required_equipment=json.loads(item.required_equipment or "[]"), preferred_days=json.loads(item.preferred_days or "[]")) for item in db.query(CourseSectionModel).order_by(CourseSectionModel.id).all()]
    finally: db.close()

@router.put("/sections/{section_id}", response_model=CourseSection, tags=["Sections"], dependencies=[Depends(require_roles("ADMIN"))])
def update_section(section_id: int, item: CourseSection):
    db = SessionLocal()
    try:
        record = db.get(CourseSectionModel, section_id)
        if not record:
            raise HTTPException(404, "Section không tồn tại.")
        if not db.get(TeacherModel, item.teacher_id) or not db.get(StudentClassModel, item.class_id):
            raise HTTPException(400, "Teacher hoặc class tham chiếu không tồn tại.")
        record.name, record.teacher_id, record.class_id = item.name, item.teacher_id, item.class_id
        record.num_slots, record.expected_size = item.num_slots, item.expected_size
        record.required_room_type = item.required_room_type
        record.required_equipment = json.dumps(item.required_equipment)
        record.preferred_days = json.dumps(item.preferred_days)
        db.commit()
        return item.model_copy(update={"id": section_id})
    finally:
        db.close()

@router.delete("/sections/{section_id}", tags=["Sections"], dependencies=[Depends(require_roles("ADMIN"))])
def delete_section(section_id: int):
    db = SessionLocal()
    try:
        record = db.get(CourseSectionModel, section_id)
        if not record:
            raise HTTPException(404, "Section không tồn tại.")
        if db.query(ScheduleModel).filter(ScheduleModel.section_id == section_id).first():
            raise HTTPException(409, "Không thể xóa section đã có timetable assignment.")
        db.delete(record); db.commit(); return {"deleted": section_id}
    finally:
        db.close()

@router.get("/system/status", response_model=Dict, tags=["System"])
def system_status():
    database_status = "CONNECTED"
    try:
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
    except Exception:
        database_status = "ERROR"
    return {"api": "ONLINE", "database": database_status, "ortools": "READY", "ai_engine": "READY", "status": "HEALTHY" if database_status == "CONNECTED" else "DEGRADED"}

@router.get("/dashboard/metrics", response_model=Dict, tags=["Dashboard"], dependencies=[Depends(require_roles("ADMIN"))])
def dashboard_metrics(version: str = Query("HK1_2026_V1")):
    db = SessionLocal()
    try:
        records = db.query(ScheduleModel).filter(ScheduleModel.version == version).all(); metadata = db.query(ScheduleVersionModel).filter(ScheduleVersionModel.version == version).first(); reschedules = db.query(RescheduleEventModel).filter(RescheduleEventModel.target_version == version).count()
    finally: db.close()
    if not records: return {"version": version, "total_classes_scheduled": 0, "total_assignments": 0, "total_rooms": metadata.total_rooms if metadata else 0, "room_utilization_rate": "0.0%", "quality_score": metadata.quality_score if metadata else None, "status": "NO_DATA"}
    rooms = metadata.total_rooms if metadata and metadata.total_rooms else len({item.room_id for item in records}); days = metadata.total_days if metadata and metadata.total_days else 6; slots = metadata.total_slots if metadata and metadata.total_slots else 10
    return {"version": version, "total_classes_scheduled": len({item.section_id for item in records}), "total_assignments": len(records), "total_rooms": rooms, "room_utilization_rate": f"{round(len(records) / max(1, rooms * days * slots) * 100, 2)}%", "saturday_slots": sum(item.day == 7 for item in records), "reschedule_count": reschedules, "conflict_count": metadata.conflict_count if metadata else 0, "quality_score": metadata.quality_score if metadata else None, "teacher_gap": metadata.teacher_gap if metadata else 0, "student_gap": metadata.student_gap if metadata else 0, "preference_satisfaction": metadata.preference_satisfaction if metadata else None, "consecutive_overload": metadata.consecutive_overload if metadata else 0, "status": "HEALTHY"}

@router.get("/dashboard/conflicts", response_model=List[str], tags=["Dashboard"], dependencies=[Depends(require_roles("ADMIN"))])
def dashboard_conflicts(version: str = Query("HK1_2026_V1")):
    db = SessionLocal()
    try: records = db.query(ScheduleModel).filter(ScheduleModel.version == version).all()
    finally: db.close()
    occupied = set(); conflicts = []
    for item in records:
        key = (item.room_id, item.day, item.slot)
        if key in occupied: conflicts.append(f"Room conflict at Room {item.room_id}, Day {item.day}, Slot {item.slot}")
        occupied.add(key)
    return conflicts

@router.post("/preferences/feedback", tags=["Preferences"])
def feedback(item: PreferenceFeedback, user=Depends(require_roles("TEACHER"))):
    if item.entity_type.upper() not in {"TEACHER", "SECTION", "CLASS"}: raise HTTPException(400, "entity_type không hợp lệ.")
    if item.entity_type.upper() == "TEACHER" and item.entity_id != user.get("teacher_id"):
        raise HTTPException(403, "Teacher chỉ được gửi preference cho chính mình.")
    db = SessionLocal()
    try: db.add(HistoricalPreferenceModel(entity_type=item.entity_type.upper(), entity_id=item.entity_id, day=item.day, slot=item.slot, satisfaction_score=item.satisfaction)); db.commit()
    finally: db.close()
    return {"status": "recorded"}

@router.get("/preferences/recommendations/{teacher_id}", response_model=List[Dict], tags=["Preferences"])
def recommendations(teacher_id: int, threshold: float = Query(.75, ge=0, le=1), user=Depends(current_user)):
    if user.get("role") != "ADMIN" and user.get("teacher_id") != teacher_id:
        raise HTTPException(403, "Không được xem recommendation của teacher khác.")
    db = SessionLocal()
    try:
        scores = AIPreferenceRecommender(db).teacher_preference_scores(teacher_id)
        return [{"day": day, "slot": slot, "score": score / 100, "source": "historical"} for (day, slot), score in sorted(scores.items()) if score / 100 >= threshold]
    finally: db.close()

@router.get("/preferences/teacher/{teacher_id}", response_model=List[Dict], tags=["Preferences"])
def preference_history(teacher_id: int, user=Depends(current_user)):
    if user.get("role") != "ADMIN" and user.get("teacher_id") != teacher_id:
        raise HTTPException(403, "Không được xem lịch sử của teacher khác.")
    db = SessionLocal()
    try:
        rows = db.query(HistoricalPreferenceModel).filter(HistoricalPreferenceModel.entity_type == "TEACHER", HistoricalPreferenceModel.entity_id == teacher_id).all()
        grouped = {}
        for row in rows: grouped.setdefault((row.day, row.slot), []).append(row.satisfaction_score or 0)
        return [{"day": day, "slot": slot, "average_satisfaction": round(sum(values) / len(values), 4), "feedback_count": len(values)} for (day, slot), values in sorted(grouped.items())]
    finally: db.close()
