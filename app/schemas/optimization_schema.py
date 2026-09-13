from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

class Teacher(BaseModel):
    id: int
    name: str
    unavailable_slots: List[Tuple[int, int]] = Field(default_factory=list)
    preferred_slots: List[Tuple[int, int]] = Field(default_factory=list)

class Room(BaseModel):
    id: int
    name: str
    capacity: int
    room_type: str = "THEORY"
    equipment: List[str] = Field(default_factory=list)

class StudentClass(BaseModel):
    id: int
    name: str
    size: int

class CourseSection(BaseModel):
    id: int
    name: str
    teacher_id: int
    class_id: int
    num_slots: int
    expected_size: Optional[int] = None
    required_room_type: str = "THEORY"
    required_equipment: List[str] = Field(default_factory=list)
    preferred_days: List[int] = Field(default_factory=list)

class TimetableAssignment(BaseModel):
    section_id: int
    room_id: int
    day: int
    slot: int

class OptimizationReport(BaseModel):
    objective_value: float
    teacher_gap_penalty: int
    student_gap_penalty: int
    saturday_penalty: int
    preference_penalty: int
    consecutive_penalty: int
    disturbance_penalty: int = 0
    preference_reward: int = 0

class EvaluationResult(BaseModel):
    score: float
    total_teacher_gaps: int
    total_student_gaps: int
    saturday_slots: int
    consecutive_violations: int
    unpreferred_day_violations: int
    teacher_preference_violations: int
    hard_constraint_violations: int = 0
    quality_details: Dict[str, float] = Field(default_factory=dict)
    report: OptimizationReport

class TimetableResponse(BaseModel):
    assignments: List[TimetableAssignment]
    evaluation: EvaluationResult
    conflicts: List[str]

class TimetableRequest(BaseModel):
    teachers: List[Teacher]
    rooms: List[Room]
    student_classes: List[StudentClass]
    sections: List[CourseSection]
    days: List[int] = Field(default_factory=lambda: list(range(2, 8)))
    slots: List[int] = Field(default_factory=lambda: list(range(1, 11)))
    max_consecutive_slots: int = Field(default=3, ge=1)

class RescheduleRequest(BaseModel):
    version: str
    affected_teacher_id: Optional[int] = None
    affected_room_id: Optional[int] = None
    unavailable_slots: List[Tuple[int, int]] = Field(default_factory=list)
    reason: Optional[str] = None

class RollbackRequest(BaseModel):
    target_version: str
    new_version: Optional[str] = None

class PreferenceFeedback(BaseModel):
    entity_type: str = "TEACHER"
    entity_id: int
    day: int
    slot: int
    satisfaction: float = Field(ge=0.0, le=1.0)
