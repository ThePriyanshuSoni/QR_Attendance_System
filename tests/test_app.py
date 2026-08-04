from pathlib import Path

import pytest

from app import create_app, get_db


@pytest.fixture()
def app(tmp_path: Path):
    database = tmp_path / "test.db"
    app = create_app({"TESTING": True, "DATABASE": str(database), "SECRET_KEY": "test"})
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client):
    return client.post("/login", data={"username": "admin", "password": "admin123"})


def test_login_and_dashboard(client):
    response = login(client)
    assert response.status_code == 302
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_student_creation_and_duplicate_prevention(app, client):
    login(client)
    response = client.post(
        "/students/new",
        data={
            "admission_no": "A001",
            "name": "Test Student",
            "class_name": "6",
            "section": "A",
            "roll_no": "1",
            "parent_phone": "9999999999",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Student registered" in response.data

    with app.app_context():
        student = get_db().execute("SELECT * FROM students WHERE admission_no = 'A001'").fetchone()
        assert student is not None
        assert student["qr_token"].startswith("STU-")


def test_qr_scan_marks_attendance(app, client):
    login(client)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO students
            (admission_no, name, class_name, section, roll_no, qr_token)
            VALUES ('A002', 'QR Student', '6', 'A', '2', 'STU-TEST-QR')
            """
        )
        user_id = db.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO attendance_sessions
            (class_name, section, subject, period, attendance_date, created_by)
            VALUES ('6', 'A', 'Math', '1', '2026-08-04', ?)
            """,
            (user_id,),
        )
        session_id = cursor.lastrowid
        db.commit()

    response = client.post(f"/api/sessions/{session_id}/scan", json={"token": "STU-TEST-QR"})
    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    duplicate = client.post(f"/api/sessions/{session_id}/scan", json={"token": "STU-TEST-QR"})
    assert duplicate.status_code == 409
    assert duplicate.get_json()["duplicate"] is True


def test_qr_image_scan_marks_attendance(app, client):
    import io
    import qrcode

    login(client)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO students
            (admission_no, name, class_name, section, roll_no, qr_token)
            VALUES ('A003', 'Image QR Student', '7', 'B', '1', 'STU-IMAGE-QR')
            """
        )
        user_id = db.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()["id"]
        cursor = db.execute(
            """
            INSERT INTO attendance_sessions
            (class_name, section, subject, period, attendance_date, created_by)
            VALUES ('7', 'B', 'Science', '2', '2026-08-04', ?)
            """,
            (user_id,),
        )
        session_id = cursor.lastrowid
        db.commit()

    image = qrcode.make("STU-IMAGE-QR")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    response = client.post(
        f"/api/sessions/{session_id}/scan-image",
        data={"image": (buffer, "student-qr.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
