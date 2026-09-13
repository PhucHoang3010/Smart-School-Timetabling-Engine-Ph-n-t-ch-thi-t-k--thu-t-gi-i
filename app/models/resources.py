from sqlalchemy import Column, ForeignKey, Integer, String
from ..core.database import Base

class TeacherModel(Base):
    __tablename__ = "teachers"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    unavailable_slots = Column(String(2000), default="[]")
    preferred_slots = Column(String(2000), default="[]")

class StudentClassModel(Base):
    __tablename__ = "student_classes"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)

class RoomModel(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    capacity = Column(Integer, nullable=False)
    room_type = Column(String(30), nullable=False)
    equipment = Column(String(1000), nullable=True)

class CourseSectionModel(Base):
    __tablename__ = "course_sections"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("student_classes.id"), nullable=False, index=True)
    num_slots = Column(Integer, nullable=False)
    required_room_type = Column(String(30), nullable=False)
    expected_size = Column(Integer, nullable=True)
    required_equipment = Column(String(2000), default="[]")
    preferred_days = Column(String(500), default="[]")
