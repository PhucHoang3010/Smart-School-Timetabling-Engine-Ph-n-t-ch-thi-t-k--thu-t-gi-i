import unittest
from unittest.mock import patch

from app.ai_engine.preference_recommender import AIPreferenceRecommender
from app.api.v1.optimization_router import compare_timetables
from app.core.database import SessionLocal
from app.schemas.optimization_schema import CourseSection, OptimizationReport, Room, StudentClass, Teacher, TimetableAssignment
from app.services.optimization_service import DatabaseService
from app.solver.cpsat_engine import SmartTimetablingEngine
from app.solver.evaluator import TimetableEvaluator
from app.validators.domain_validator import DataValidationError, TimetableValidator


class TimetablingTests(unittest.TestCase):
    def setUp(self):
        self.teachers = [Teacher(id=1, name="Teacher A")]
        self.rooms = [Room(id=1, name="Room A", capacity=30)]
        self.classes = [StudentClass(id=1, name="Class A", size=20)]
        self.sections = [CourseSection(id=1, name="Math", teacher_id=1, class_id=1, num_slots=3)]

    def test_valid_payload(self):
        TimetableValidator.validate(self.teachers, self.rooms, self.classes, self.sections)

    def test_validator_rejects_invalid_references_and_ranges(self):
        invalid_section = CourseSection(id=1, name="Math", teacher_id=99, class_id=99, num_slots=11)
        with self.assertRaises(DataValidationError) as context:
            TimetableValidator.validate(self.teachers, self.rooms, self.classes, [invalid_section])
        self.assertTrue(any("Teacher ID" in error for error in context.exception.errors))
        self.assertTrue(any("num_slots" in error for error in context.exception.errors))

    def test_validator_rejects_missing_equipment(self):
        section = self.sections[0].model_copy(update={"required_equipment": ["Computer"]})
        with self.assertRaises(DataValidationError):
            TimetableValidator.validate(self.teachers, self.rooms, self.classes, [section])

    def test_section_slots_are_one_contiguous_block(self):
        assignments, _ = SmartTimetablingEngine(
            self.teachers, self.rooms, self.classes, self.sections, days=[2], slots=[1, 2, 3, 4, 5]
        ).solve()
        slots = sorted(assignment.slot for assignment in assignments)
        self.assertEqual(len(slots), 3)
        self.assertEqual(slots, list(range(slots[0], slots[0] + 3)))

    def test_section_is_infeasible_when_day_has_too_few_slots(self):
        assignments, _ = SmartTimetablingEngine(
            self.teachers, self.rooms, self.classes, self.sections, days=[2], slots=[1, 2]
        ).solve()
        self.assertEqual(assignments, [])

    def test_teacher_incident_is_blocked(self):
        assignments, _ = SmartTimetablingEngine(
            self.teachers, self.rooms, self.classes,
            [self.sections[0].model_copy(update={"num_slots": 1})], days=[2], slots=[1, 2]
        ).solve(incident_slots=[("teacher", 1, 2, 1)])
        self.assertTrue(all(assignment.slot != 1 for assignment in assignments))

    def test_room_incident_is_blocked_without_blocking_other_room(self):
        rooms = [self.rooms[0], Room(id=2, name="Room B", capacity=30)]
        section = self.sections[0].model_copy(update={"num_slots": 1})
        assignments, _ = SmartTimetablingEngine(
            self.teachers, rooms, self.classes, [section], days=[2], slots=[1]
        ).solve(incident_slots=[("room", 1, 2, 1)])
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].room_id, 2)

    def test_evaluator_marks_hard_violation_as_invalid(self):
        teacher = self.teachers[0].model_copy(update={"unavailable_slots": [(2, 1)]})
        report = OptimizationReport(
            objective_value=0, teacher_gap_penalty=0, student_gap_penalty=0,
            saturday_penalty=0, preference_penalty=0, consecutive_penalty=0
        )
        conflicts, evaluation = TimetableEvaluator.evaluate(
            [TimetableAssignment(section_id=1, room_id=1, day=2, slot=1)],
            self.sections, [teacher], self.classes, report, rooms=self.rooms
        )
        self.assertTrue(any("unavailable" in conflict for conflict in conflicts))
        self.assertEqual(evaluation.score, 0)
        self.assertGreater(evaluation.hard_constraint_violations, 0)

    def test_evaluator_detects_room_teacher_and_class_conflicts(self):
        sections = [
            self.sections[0].model_copy(update={"num_slots": 1}),
            CourseSection(id=2, name="Physics", teacher_id=1, class_id=1, num_slots=1),
        ]
        assignments = [
            TimetableAssignment(section_id=1, room_id=1, day=2, slot=1),
            TimetableAssignment(section_id=2, room_id=1, day=2, slot=1),
        ]
        report = OptimizationReport(
            objective_value=0, teacher_gap_penalty=0, student_gap_penalty=0,
            saturday_penalty=0, preference_penalty=0, consecutive_penalty=0
        )
        conflicts, evaluation = TimetableEvaluator.evaluate(
            assignments, sections, self.teachers, self.classes, report, rooms=self.rooms
        )
        self.assertTrue(any("Room conflict" in conflict for conflict in conflicts))
        self.assertTrue(any("Teacher conflict" in conflict for conflict in conflicts))
        self.assertTrue(any("Class conflict" in conflict for conflict in conflicts))
        self.assertEqual(evaluation.score, 0)

    def test_teacher_incident_can_be_infeasible(self):
        section = self.sections[0].model_copy(update={"num_slots": 1})
        assignments, _ = SmartTimetablingEngine(
            self.teachers, self.rooms, self.classes, [section], days=[2], slots=[1]
        ).solve(incident_slots=[("teacher", 1, 2, 1)])
        self.assertEqual(assignments, [])

    def test_historical_preference_is_objective_reward(self):
        assignments, report = SmartTimetablingEngine(
            self.teachers, self.rooms, self.classes,
            [self.sections[0].model_copy(update={"num_slots": 1})], days=[2], slots=[1, 2],
            preference_scores={(1, 2, 2): 100}
        ).solve()
        self.assertEqual(assignments[0].slot, 2)
        self.assertEqual(report.preference_reward, 100)

    def test_compare_keeps_all_assignments_for_multi_slot_section(self):
        source = [
            TimetableAssignment(section_id=1, room_id=1, day=2, slot=1),
            TimetableAssignment(section_id=1, room_id=1, day=2, slot=2),
            TimetableAssignment(section_id=1, room_id=1, day=2, slot=3),
        ]
        target = [
            TimetableAssignment(section_id=1, room_id=1, day=2, slot=1),
            TimetableAssignment(section_id=1, room_id=1, day=2, slot=2),
            TimetableAssignment(section_id=1, room_id=1, day=2, slot=4),
        ]
        with patch.object(DatabaseService, "load_timetable", side_effect=[source, target]):
            result = compare_timetables("V1", "V2")
        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(len(result["source_assignments"][1]), 3)

    def test_recommendation_falls_back_to_empty_without_history(self):
        db = SessionLocal()
        try:
            recommender = AIPreferenceRecommender(db)
            self.assertEqual(recommender.recommend_teacher_preferences(999999), [])
            self.assertEqual(recommender.teacher_preference_scores(999999), {})
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)