from typing import Dict, List, Optional, Tuple
from ortools.sat.python import cp_model
from ..schemas.optimization_schema import CourseSection, OptimizationReport, Room, StudentClass, Teacher, TimetableAssignment
from .constraints import W_AI_PREFERENCE, W_CLASS_GAP, W_CONSECUTIVE, W_DISTURBANCE, W_PREFERENCE, W_SATURDAY, W_TEACHER_GAP, W_TEACHER_PREF

class SmartTimetablingEngine:
    def __init__(self, teachers: List[Teacher], rooms: List[Room], student_classes: List[StudentClass], sections: List[CourseSection], days: List[int] = list(range(2, 8)), slots: List[int] = list(range(1, 11)), preference_scores: Optional[Dict[Tuple[int, int, int], int]] = None, max_consecutive_slots: int = 3):
        self.teachers, self.rooms, self.student_classes, self.sections = teachers, rooms, student_classes, sections
        self.days, self.slots = days, slots
        self.class_map = {item.id: item for item in student_classes}
        self.preference_scores = preference_scores or {}
        self.max_consecutive_slots = max_consecutive_slots

    def solve(self, original_assignments: Optional[List[TimetableAssignment]] = None, incident_slots: Optional[List[Tuple[str, int, int, int]]] = None) -> Tuple[List[TimetableAssignment], OptimizationReport]:
        model = cp_model.CpModel(); x = {}; starts = {}
        for section in self.sections:
            actual_size = section.expected_size if section.expected_size is not None else self.class_map[section.class_id].size
            for room in self.rooms:
                if room.capacity < actual_size or room.room_type != section.required_room_type or not set(section.required_equipment).issubset(room.equipment):
                    continue
                for day in self.days:
                    for slot in self.slots: x[(section.id, room.id, day, slot)] = model.NewBoolVar(f"x_{section.id}_{room.id}_{day}_{slot}")
                    for start_index in range(max(0, len(self.slots) - section.num_slots + 1)):
                        start_slot = self.slots[start_index]; starts[(section.id, room.id, day, start_slot)] = model.NewBoolVar(f"start_{section.id}_{room.id}_{day}_{start_slot}")
        for section in self.sections:
            section_starts = [value for key, value in starts.items() if key[0] == section.id]
            model.Add(sum(section_starts) == 1)
            for room in self.rooms:
                for day in self.days:
                    for slot_index, slot in enumerate(self.slots):
                        covering = [starts[(section.id, room.id, day, self.slots[start])] for start in range(max(0, len(self.slots) - section.num_slots + 1)) if start <= slot_index < start + section.num_slots and (section.id, room.id, day, self.slots[start]) in starts]
                        if (section.id, room.id, day, slot) in x: model.Add(x[(section.id, room.id, day, slot)] == sum(covering))
        for room in self.rooms:
            for day in self.days:
                for slot in self.slots: model.Add(sum(x[key] for key in x if key[1:] == (room.id, day, slot)) <= 1)
        for teacher in self.teachers:
            section_ids = {section.id for section in self.sections if section.teacher_id == teacher.id}
            for day in self.days:
                for slot in self.slots:
                    values = [x[key] for key in x if key[0] in section_ids and key[2:] == (day, slot)]
                    model.Add(sum(values) <= 1)
                    if (day, slot) in teacher.unavailable_slots:
                        for value in values: model.Add(value == 0)
        for student_class in self.student_classes:
            section_ids = {section.id for section in self.sections if section.class_id == student_class.id}
            for day in self.days:
                for slot in self.slots: model.Add(sum(x[key] for key in x if key[0] in section_ids and key[2:] == (day, slot)) <= 1)
        if incident_slots:
            for incident in incident_slots:
                entity_type, entity_id, day, slot = ("teacher", *incident) if len(incident) == 3 else incident
                for section in self.sections:
                    for room in self.rooms:
                        if ((entity_type == "teacher" and section.teacher_id == entity_id) or (entity_type == "room" and room.id == entity_id)) and (section.id, room.id, day, slot) in x: model.Add(x[(section.id, room.id, day, slot)] == 0)
        teacher_gaps, class_gaps, saturday, preference, teacher_preference, overload, disturbance, ai_reward = [], [], [], [], [], [], [], []
        def gap_vars(entity_type, entities, get_ids):
            result = []
            for entity in entities:
                ids = get_ids(entity.id)
                for day in self.days:
                    occupied = {}
                    for slot in self.slots:
                        occupied[slot] = model.NewBoolVar(f"{entity_type}_{entity.id}_{day}_{slot}")
                        model.Add(occupied[slot] == sum(x[key] for key in x if key[0] in ids and key[2:] == (day, slot)))
                    for slot in self.slots[1:-1]:
                        before = model.NewBoolVar(f"before_{entity_type}_{entity.id}_{day}_{slot}"); after = model.NewBoolVar(f"after_{entity_type}_{entity.id}_{day}_{slot}"); gap = model.NewBoolVar(f"gap_{entity_type}_{entity.id}_{day}_{slot}")
                        model.AddMaxEquality(before, [occupied[item] for item in self.slots if item < slot]); model.AddMaxEquality(after, [occupied[item] for item in self.slots if item > slot])
                        model.AddBoolAnd([occupied[slot].Not(), before, after]).OnlyEnforceIf(gap); model.AddBoolOr([occupied[slot], before.Not(), after.Not()]).OnlyEnforceIf(gap.Not()); result.append(gap)
            return result
        teacher_gaps = gap_vars("teacher", self.teachers, lambda ident: {section.id for section in self.sections if section.teacher_id == ident})
        class_gaps = gap_vars("class", self.student_classes, lambda ident: {section.id for section in self.sections if section.class_id == ident})
        saturday = [value for key, value in x.items() if key[2] == 7]
        for section in self.sections:
            for key, value in x.items():
                if key[0] == section.id and section.preferred_days and key[2] not in section.preferred_days: preference.append(value)
        for teacher in self.teachers:
            for key, value in x.items():
                if any(section.id == key[0] and section.teacher_id == teacher.id for section in self.sections) and teacher.preferred_slots and (key[2], key[3]) not in teacher.preferred_slots: teacher_preference.append(value)
        for student_class in self.student_classes:
            ids = {section.id for section in self.sections if section.class_id == student_class.id}
            for day in self.days:
                for index in range(max(0, len(self.slots) - self.max_consecutive_slots)):
                    window = self.slots[index:index + self.max_consecutive_slots + 1]; value = model.NewBoolVar(f"overload_{student_class.id}_{day}_{window[0]}"); total = sum(x[key] for key in x if key[0] in ids and key[2] == day and key[3] in window)
                    model.Add(total == len(window)).OnlyEnforceIf(value); model.Add(total <= len(window) - 1).OnlyEnforceIf(value.Not()); overload.append(value)
        for (teacher_id, day, slot), score in self.preference_scores.items():
            for section in self.sections:
                if section.teacher_id == teacher_id:
                    ai_reward.extend((value, score) for key, value in x.items() if key[0] == section.id and key[2:] == (day, slot))
        if original_assignments:
            original = {(item.section_id, item.room_id, item.day, item.slot) for item in original_assignments}
            disturbance = [1 - value if key in original else value for key, value in x.items()]
        model.Minimize(sum(teacher_gaps) * W_TEACHER_GAP + sum(class_gaps) * W_CLASS_GAP + sum(saturday) * W_SATURDAY + sum(preference) * W_PREFERENCE + sum(teacher_preference) * W_TEACHER_PREF + sum(overload) * W_CONSECUTIVE + sum(disturbance) * W_DISTURBANCE - sum(value * score for value, score in ai_reward) * W_AI_PREFERENCE)
        solver = cp_model.CpSolver(); solver.parameters.max_time_in_seconds = 15; status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE): return [], OptimizationReport(objective_value=-1, teacher_gap_penalty=0, student_gap_penalty=0, saturday_penalty=0, preference_penalty=0, consecutive_penalty=0)
        assignments = [TimetableAssignment(section_id=sid, room_id=rid, day=day, slot=slot) for (sid, rid, day, slot), value in x.items() if solver.Value(value)]
        return assignments, OptimizationReport(objective_value=solver.ObjectiveValue(), teacher_gap_penalty=sum(solver.Value(value) for value in teacher_gaps) * W_TEACHER_GAP, student_gap_penalty=sum(solver.Value(value) for value in class_gaps) * W_CLASS_GAP, saturday_penalty=sum(solver.Value(value) for value in saturday) * W_SATURDAY, preference_penalty=(sum(solver.Value(value) for value in preference) * W_PREFERENCE + sum(solver.Value(value) for value in teacher_preference) * W_TEACHER_PREF), consecutive_penalty=sum(solver.Value(value) for value in overload) * W_CONSECUTIVE, disturbance_penalty=sum(solver.Value(value) for value in disturbance) * W_DISTURBANCE, preference_reward=sum(solver.Value(value) * score for value, score in ai_reward))
