from typing import Dict, List, Optional, Tuple
from ..schemas.optimization_schema import CourseSection, EvaluationResult, OptimizationReport, Room, StudentClass, Teacher, TimetableAssignment

class TimetableEvaluator:
    @staticmethod
    def evaluate(assignments: List[TimetableAssignment], sections: List[CourseSection], teachers: List[Teacher], student_classes: List[StudentClass], report: OptimizationReport, max_consecutive_slots: int = 3, rooms: Optional[List[Room]] = None) -> Tuple[List[str], EvaluationResult]:
        conflicts, hard = [], 0
        sec_map = {item.id: item for item in sections}; teacher_map = {item.id: item for item in teachers}; class_map = {item.id: item for item in student_classes}; room_map = {item.id: item for item in rooms or []}
        occupied_rooms, occupied_teachers, occupied_classes = set(), set(), set(); section_records: Dict[int, List[TimetableAssignment]] = {}
        for assignment in assignments:
            section = sec_map.get(assignment.section_id)
            if not section:
                conflicts.append(f"Unknown section {assignment.section_id}"); hard += 1; continue
            section_records.setdefault(section.id, []).append(assignment)
            if (assignment.room_id, assignment.day, assignment.slot) in occupied_rooms: conflicts.append(f"Room conflict at Room {assignment.room_id}, Day {assignment.day}, Slot {assignment.slot}"); hard += 1
            if (section.teacher_id, assignment.day, assignment.slot) in occupied_teachers: conflicts.append(f"Teacher conflict at Teacher {section.teacher_id}, Day {assignment.day}, Slot {assignment.slot}"); hard += 1
            if (section.class_id, assignment.day, assignment.slot) in occupied_classes: conflicts.append(f"Class conflict at Class {section.class_id}, Day {assignment.day}, Slot {assignment.slot}"); hard += 1
            teacher = teacher_map.get(section.teacher_id); room = room_map.get(assignment.room_id)
            if teacher is None: conflicts.append(f"Unknown teacher {section.teacher_id}"); hard += 1
            if section.class_id not in class_map: conflicts.append(f"Unknown class {section.class_id}"); hard += 1
            if assignment.day not in range(2, 8) or assignment.slot not in range(1, 11): conflicts.append(f"Invalid day/slot at section {section.id}"); hard += 1
            if teacher and (assignment.day, assignment.slot) in teacher.unavailable_slots: conflicts.append(f"Teacher unavailable at Teacher {section.teacher_id}, Day {assignment.day}, Slot {assignment.slot}"); hard += 1
            if room:
                expected_size = section.expected_size or class_map.get(section.class_id, StudentClass(id=0, name="", size=0)).size
                if room.capacity < expected_size: conflicts.append(f"Room capacity conflict at Room {room.id}"); hard += 1
                if room.room_type != section.required_room_type: conflicts.append(f"Room type conflict at Room {room.id}"); hard += 1
                if set(section.required_equipment) - set(room.equipment): conflicts.append(f"Missing equipment at Room {room.id}"); hard += 1
            elif rooms: conflicts.append(f"Unknown room {assignment.room_id}"); hard += 1
            occupied_rooms.add((assignment.room_id, assignment.day, assignment.slot)); occupied_teachers.add((section.teacher_id, assignment.day, assignment.slot)); occupied_classes.add((section.class_id, assignment.day, assignment.slot))
        for section in sections:
            records = section_records.get(section.id, [])
            if len(records) != section.num_slots: conflicts.append(f"Section {section.id} duration mismatch"); hard += 1
            if records and len({(item.room_id, item.day) for item in records}) != 1: conflicts.append(f"Section {section.id} is split across rooms or days"); hard += 1
            slots = sorted(item.slot for item in records)
            if slots and slots != list(range(slots[0], slots[0] + len(slots))): conflicts.append(f"Section {section.id} slots are not contiguous"); hard += 1
        valid = [item for item in assignments if item.section_id in sec_map]
        def gaps(get_id):
            grouped: Dict[Tuple[int, int], List[int]] = {}
            for item in valid:
                section = sec_map[item.section_id]; grouped.setdefault((get_id(section), item.day), []).append(item.slot)
            return sum(max(0, max(slots) - min(slots) + 1 - len(slots)) for slots in grouped.values() if len(slots) > 1)
        teacher_gaps, class_gaps = gaps(lambda section: section.teacher_id), gaps(lambda section: section.class_id)
        saturday = sum(item.day == 7 for item in valid)
        unpreferred = sum(bool(sec_map[item.section_id].preferred_days) and item.day not in sec_map[item.section_id].preferred_days for item in valid)
        teacher_pref = sum(bool(teacher_map.get(sec_map[item.section_id].teacher_id, Teacher(id=0, name="")).preferred_slots) and (item.day, item.slot) not in teacher_map[sec_map[item.section_id].teacher_id].preferred_slots for item in valid if sec_map[item.section_id].teacher_id in teacher_map)
        class_slots: Dict[Tuple[int, int], List[int]] = {}
        for item in valid: class_slots.setdefault((sec_map[item.section_id].class_id, item.day), []).append(item.slot)
        overload = 0
        for slots in class_slots.values():
            run = 1; ordered = sorted(set(slots))
            for previous, current in zip(ordered, ordered[1:]):
                if current == previous + 1: run += 1
                else: overload += max(0, run - max_consecutive_slots); run = 1
            overload += max(0, run - max_consecutive_slots) if ordered else 0
        deductions = min(30, teacher_gaps * 3) + min(20, class_gaps * 2) + min(15, saturday * 3) + min(15, (unpreferred + teacher_pref) * 2) + min(20, overload * 5)
        score = 0.0 if hard else max(0.0, round(100 - deductions, 2))
        details = {"teacher_gap_score": max(0.0, 100 - min(100, teacher_gaps * 3)), "student_gap_score": max(0.0, 100 - min(100, class_gaps * 2)), "saturday_score": max(0.0, 100 - min(100, saturday * 3)), "preference_score": max(0.0, 100 - min(100, (unpreferred + teacher_pref) * 2)), "consecutive_score": max(0.0, 100 - min(100, overload * 5)), "conflict_score": 100.0 if not conflicts else 0.0}
        return conflicts, EvaluationResult(score=score, total_teacher_gaps=teacher_gaps, total_student_gaps=class_gaps, saturday_slots=saturday, consecutive_violations=overload, unpreferred_day_violations=unpreferred, teacher_preference_violations=teacher_pref, hard_constraint_violations=hard, quality_details=details, report=report)
