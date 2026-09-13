import unittest

from fastapi.testclient import TestClient

from app.main import app


class ApiFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        admin_login = cls.client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        teacher_login = cls.client.post("/api/v1/auth/login", json={"username": "teacher1", "password": "teacher123"})
        assert admin_login.status_code == 200, admin_login.text
        assert teacher_login.status_code == 200, teacher_login.text
        cls.admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        cls.teacher_headers = {"Authorization": f"Bearer {teacher_login.json()['access_token']}"}
        cls.payload = {
            "teachers": [{"id": 1, "name": "Teacher Flow"}],
            "rooms": [{"id": 201, "name": "Room Flow", "capacity": 40, "room_type": "THEORY"}],
            "student_classes": [{"id": 301, "name": "Class Flow", "size": 25}],
            "sections": [{
                "id": 401,
                "name": "Course Flow",
                "teacher_id": 1,
                "class_id": 301,
                "num_slots": 2,
                "required_room_type": "THEORY"
            }],
            "days": [2],
            "slots": [1, 2, 3, 4],
            "max_consecutive_slots": 3
        }
        cls.version = "FLOW_TEST_V1"

    def test_generate_returns_contiguous_timetable(self):
        response = self.client.post("/api/v1/timetables/generate", headers=self.admin_headers, json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["assignments"]), 2)
        slots = sorted(item["slot"] for item in body["assignments"])
        self.assertEqual(slots, list(range(slots[0], slots[0] + 2)))
        self.assertEqual(body["evaluation"]["hard_constraint_violations"], 0)

    def test_teacher_cannot_generate_admin_timetable(self):
        response = self.client.post("/api/v1/timetables/generate", headers=self.teacher_headers, json=self.payload)
        self.assertEqual(response.status_code, 403)

    def test_save_dashboard_feedback_and_recommendation_flow(self):
        response = self.client.post(
            "/api/v1/timetables/generate-and-save",
            params={"version": self.version},
            headers=self.admin_headers,
            json=self.payload,
        )
        self.assertEqual(response.status_code, 200, response.text)

        metrics = self.client.get("/api/v1/dashboard/metrics", headers=self.admin_headers, params={"version": self.version})
        self.assertEqual(metrics.status_code, 200, metrics.text)
        self.assertEqual(metrics.json()["total_assignments"], 2)
        self.assertIsNotNone(metrics.json()["quality_score"])

        feedback = self.client.post("/api/v1/preferences/feedback", headers=self.teacher_headers, json={
            "entity_type": "TEACHER",
            "entity_id": 1,
            "day": 2,
            "slot": 2,
            "satisfaction": 1.0,
        })
        self.assertEqual(feedback.status_code, 200, feedback.text)

        recommendations = self.client.get("/api/v1/preferences/recommendations/1", headers=self.teacher_headers)
        self.assertEqual(recommendations.status_code, 200, recommendations.text)
        self.assertTrue(any(item["day"] == 2 and item["slot"] == 2 for item in recommendations.json()))

    def test_reschedule_flow_returns_new_version_schedule(self):
        saved = self.client.post(
            "/api/v1/timetables/generate-and-save",
            params={"version": self.version},
            headers=self.admin_headers,
            json=self.payload,
        )
        self.assertEqual(saved.status_code, 200, saved.text)

        response = self.client.post(
            "/api/v1/timetables/auto-reschedule",
            headers=self.admin_headers,
            json={
                "payload": self.payload,
                "incident": {
                    "version": self.version,
                    "affected_room_id": 201,
                    "unavailable_slots": [[2, 2]],
                    "reason": "Room maintenance"
                }
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["assignments"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
