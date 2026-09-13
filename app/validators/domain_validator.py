from typing import List, Optional
from ..schemas.optimization_schema import CourseSection, Room, StudentClass, Teacher

class DataValidationError(Exception):
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))

class TimetableValidator:
    @staticmethod
    def validate(teachers: List[Teacher], rooms: List[Room], student_classes: List[StudentClass],
                 sections: List[CourseSection], days: Optional[List[int]] = None,
                 slots: Optional[List[int]] = None):
        errors = []
        allowed_days = set(days or range(2, 8))
        allowed_slots = set(slots or range(1, 11))
        if not allowed_days or not allowed_days.issubset(set(range(2, 8))):
            errors.append("days phải là các giá trị trong khoảng 2-7 và không được rỗng.")
        if not allowed_slots or not allowed_slots.issubset(set(range(1, 11))):
            errors.append("slots phải là các giá trị trong khoảng 1-10 và không được rỗng.")
        def duplicates(items, label):
            ids = [item.id for item in items]
            repeated = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
            if repeated:
                errors.append(f"{label}: ID bị trùng {repeated}.")
        duplicates(teachers, "Teachers")
        duplicates(rooms, "Rooms")
        duplicates(student_classes, "Student classes")
        duplicates(sections, "Sections")
        teacher_ids = {item.id for item in teachers}
        class_map = {item.id: item for item in student_classes}
        room_types = {item.room_type for item in rooms}
        available_equipment = {equipment for room in rooms for equipment in room.equipment}
        for teacher in teachers:
            for day, slot in teacher.unavailable_slots + teacher.preferred_slots:
                if day not in allowed_days or slot not in allowed_slots:
                    errors.append(f"Teacher {teacher.id}: day/slot không hợp lệ ({day}, {slot}).")
        for room in rooms:
            if room.capacity <= 0:
                errors.append(f"Room {room.id}: capacity phải lớn hơn 0.")
        for student_class in student_classes:
            if student_class.size <= 0:
                errors.append(f"Class {student_class.id}: size phải lớn hơn 0.")
        for section in sections:
            if section.teacher_id not in teacher_ids:
                errors.append(f"Section {section.id} ({section.name}): Teacher ID {section.teacher_id} không tồn tại.")
            if section.class_id not in class_map:
                errors.append(f"Section {section.id} ({section.name}): Class ID {section.class_id} không tồn tại.")
            if section.required_room_type not in room_types:
                errors.append(f"Section {section.id}: Không tìm thấy loại phòng '{section.required_room_type}'.")
            if section.num_slots < 1 or section.num_slots > len(allowed_slots):
                errors.append(f"Section {section.id}: num_slots vượt quá số slot khả dụng ({len(allowed_slots)}).")
            invalid_days = [day for day in section.preferred_days if day not in allowed_days]
            if invalid_days:
                errors.append(f"Section {section.id}: preferred_days không hợp lệ {invalid_days}.")
            missing = sorted(set(section.required_equipment) - available_equipment)
            if missing:
                errors.append(f"Section {section.id}: thiết bị không tồn tại {missing}.")
            expected_size = section.expected_size if section.expected_size is not None else class_map.get(section.class_id, StudentClass(id=0, name="", size=0)).size
            valid_rooms = [room for room in rooms if room.room_type == section.required_room_type and room.capacity >= expected_size and set(section.required_equipment).issubset(room.equipment)]
            if not valid_rooms:
                errors.append(f"Section {section.id}: Không có phòng phù hợp sức chứa/loại/thiết bị.")
        if errors:
            raise DataValidationError(errors)
