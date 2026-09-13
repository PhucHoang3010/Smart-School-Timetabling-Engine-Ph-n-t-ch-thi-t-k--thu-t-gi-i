import unittest

from fastapi.testclient import TestClient

from app.main import app


class DemoAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        admin = cls.client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        teacher = cls.client.post("/api/v1/auth/login", json={"username": "teacher1", "password": "teacher123"})
        assert admin.status_code == 200
        assert teacher.status_code == 200
        cls.admin_token = admin.json()["access_token"]
        cls.teacher_token = teacher.json()["access_token"]
        cls.admin = {"Authorization": f"Bearer {cls.admin_token}"}
        cls.teacher = {"Authorization": f"Bearer {cls.teacher_token}"}
        cls.payload = {
            "teachers": [{"id": 1, "name": "Teacher Demo"}],
            "rooms": [{"id": 9901, "name": "Demo Room", "capacity": 40, "room_type": "THEORY", "equipment": ["Projector"]}],
            "student_classes": [{"id": 9901, "name": "Demo Class", "size": 25}],
            "sections": [{"id": 9901, "name": "Demo Course", "teacher_id": 1, "class_id": 9901, "num_slots": 2, "required_room_type": "THEORY", "required_equipment": ["Projector"]}],
            "days": [2, 3],
            "slots": [1, 2, 3, 4],
            "max_consecutive_slots": 3,
        }

    def test_01_admin_login_and_teacher_login(self):
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=self.admin).json()["role"], "ADMIN")
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=self.teacher).json()["role"], "TEACHER")

    def test_02_wrong_login_is_rejected(self):
        response = self.client.post("/api/v1/auth/login", json={"username": "teacher1", "password": "wrong_password"})
        self.assertEqual(response.status_code, 401)
        self.assertIn("không chính xác", response.json()["detail"])

    def test_03_teacher_cannot_use_admin_generate(self):
        response = self.client.post("/api/v1/timetables/generate", headers=self.teacher, json=self.payload)
        self.assertEqual(response.status_code, 403)

    def test_04_teacher_preference_and_ai_reward(self):
        for slot, score in ((1, 0.0), (2, 1.0)):
            response = self.client.post("/api/v1/preferences/feedback", headers=self.teacher, json={"entity_type": "TEACHER", "entity_id": 1, "day": 2, "slot": slot, "satisfaction": score})
            self.assertEqual(response.status_code, 200, response.text)
        recommendations = self.client.get("/api/v1/preferences/recommendations/1", headers=self.teacher)
        self.assertEqual(recommendations.status_code, 200)
        self.assertTrue(any(item["slot"] == 2 for item in recommendations.json()))
        payload = {**self.payload, "sections": [{**self.payload["sections"][0], "num_slots": 1}], "slots": [1, 2]}
        response = self.client.post("/api/v1/timetables/generate", headers=self.admin, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreaterEqual(response.json()["evaluation"]["report"]["preference_reward"], 0)

    def test_05_hard_constraints_and_room_equipment(self):
        response = self.client.post("/api/v1/timetables/generate", headers=self.admin, json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["evaluation"]["hard_constraint_violations"], 0)
        self.assertEqual(len(body["assignments"]), 2)
        self.assertEqual({item["room_id"] for item in body["assignments"]}, {9901})

    def test_06_invalid_reference_and_infeasible_room(self):
        invalid = {**self.payload, "sections": [{**self.payload["sections"][0], "teacher_id": 9999}]}
        self.assertEqual(self.client.post("/api/v1/timetables/generate", headers=self.admin, json=invalid).status_code, 400)
        no_room = {**self.payload, "student_classes": [{"id": 9902, "name": "Large", "size": 100}], "sections": [{**self.payload["sections"][0], "class_id": 9902}]}
        self.assertEqual(self.client.post("/api/v1/timetables/generate", headers=self.admin, json=no_room).status_code, 400)

    def test_07_version_compare_rollback_dashboard_and_reschedule(self):
        for version in ("ACCEPT_V1", "ACCEPT_V2"):
            self.client.delete(f"/api/v1/timetables/{version}", headers=self.admin)
            response = self.client.post("/api/v1/timetables/generate-and-save", headers=self.admin, params={"version": version}, json=self.payload)
            self.assertEqual(response.status_code, 200, response.text)
        versions = self.client.get("/api/v1/timetables/versions", headers=self.admin)
        self.assertEqual(versions.status_code, 200)
        compare = self.client.get("/api/v1/timetables/compare", headers=self.admin, params={"source_version": "ACCEPT_V1", "target_version": "ACCEPT_V2"})
        self.assertEqual(compare.status_code, 200)
        dashboard = self.client.get("/api/v1/dashboard/metrics", headers=self.admin, params={"version": "ACCEPT_V1"})
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("quality_score", dashboard.json())
        incident = {"version": "ACCEPT_V1", "affected_room_id": 9901, "unavailable_slots": [[2, 1]], "reason": "Room maintenance"}
        rescheduled = self.client.post("/api/v1/timetables/auto-reschedule", headers=self.admin, json={"payload": self.payload, "incident": incident})
        self.assertEqual(rescheduled.status_code, 200, rescheduled.text)
        self.assertTrue(all(not (item["room_id"] == 9901 and item["day"] == 2 and item["slot"] == 1) for item in rescheduled.json()["assignments"]))
        rollback = self.client.post("/api/v1/timetables/ACCEPT_ROLLBACK/rollback", headers=self.admin, json={"target_version": "ACCEPT_V1"})
        self.assertEqual(rollback.status_code, 200, rollback.text)

    def test_08_logout_revokes_admin_token(self):
        login = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        logout_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = self.client.post("/api/v1/auth/logout", headers=logout_headers)
        self.assertEqual(response.status_code, 200)
        after = self.client.get("/api/v1/dashboard/metrics", headers=logout_headers)
        self.assertEqual(after.status_code, 401)

    def test_09_admin_crud_and_system_status(self):
        status = self.client.get("/api/v1/system/status", headers=self.admin)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["ortools"], "READY")
        class_id = 19876
        created = self.client.post("/api/v1/classes", headers=self.admin, json={"id": class_id, "name": "CRUD Class", "size": 20})
        self.assertEqual(created.status_code, 201, created.text)
        updated = self.client.put(f"/api/v1/classes/{class_id}", headers=self.admin, json={"id": class_id, "name": "Updated Class", "size": 22})
        self.assertEqual(updated.status_code, 200, updated.text)
        deleted = self.client.delete(f"/api/v1/classes/{class_id}", headers=self.admin)
        self.assertEqual(deleted.status_code, 200, deleted.text)

    def test_10_teacher_registration_creates_login_session(self):
        username = "new_teacher_acceptance"
        response = self.client.post("/api/v1/auth/register", json={"username": username, "password": "teacherpass123", "teacher_name": "New Teacher"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["user"]["role"], "TEACHER")
        self.assertIsNotNone(response.json()["user"]["teacher_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
