from __future__ import annotations

import base64
import csv
import io
import os
import secrets
import sqlite3
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

import qrcode
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

F = TypeVar("F", bound=Callable[..., Any])

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "change-this-key-before-real-use"),
        DATABASE=str(Path(app.instance_path) / "attendance.db"),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    register_database(app)
    register_template_helpers(app)
    register_routes(app)

    with app.app_context():
        init_db()
        seed_default_users()

    return app


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app_config("DATABASE"),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def current_app_config(key: str) -> Any:
    from flask import current_app

    return current_app.config[key]


def close_db(_: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.commit()


def seed_default_users() -> None:
    db = get_db()
    count = db.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
    if count:
        return

    db.executemany(
        """
        INSERT INTO users (username, password_hash, full_name, role)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("admin", generate_password_hash("admin123"), "School Administrator", "admin"),
            ("teacher", generate_password_hash("teacher123"), "Demo Teacher", "teacher"),
        ],
    )
    db.commit()


def register_database(app: Flask) -> None:
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command() -> None:
        init_db()
        seed_default_users()
        print("Database initialized.")


def register_template_helpers(app: Flask) -> None:
    @app.template_filter("datetime")
    def format_datetime(value: str | None) -> str:
        if not value:
            return "—"
        try:
            return datetime.fromisoformat(value).strftime("%d %b %Y, %I:%M %p")
        except ValueError:
            return value

    @app.template_filter("datefmt")
    def format_date(value: str | None) -> str:
        if not value:
            return "—"
        try:
            return date.fromisoformat(value).strftime("%d %b %Y")
        except ValueError:
            return value


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view  # type: ignore[return-value]


def admin_required(view: F) -> F:
    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        if g.user is None:
            return redirect(url_for("login"))
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view  # type: ignore[return-value]


def register_routes(app: Flask) -> None:
    @app.before_request
    def load_logged_in_user() -> None:
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
        else:
            g.user = get_db().execute(
                "SELECT id, username, full_name, role FROM users WHERE id = ?", (user_id,)
            ).fetchone()

    @app.route("/")
    def index() -> Response | str:
        if g.user:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=("GET", "POST"))
    def login() -> Response | str:
        if g.user:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            user = get_db().execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Incorrect username or password.", "danger")
            else:
                session.clear()
                session["user_id"] = user["id"]
                next_url = request.args.get("next")
                if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                    return redirect(next_url)
                return redirect(url_for("dashboard"))

        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout() -> Response:
        session.clear()
        return redirect(url_for("login"))

    @app.route("/change-password", methods=("GET", "POST"))
    @login_required
    def change_password() -> Response | str:
        if request.method == "POST":
            current = request.form.get("current_password", "")
            new = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            db = get_db()
            user = db.execute("SELECT * FROM users WHERE id = ?", (g.user["id"],)).fetchone()

            if not check_password_hash(user["password_hash"], current):
                flash("Current password is incorrect.", "danger")
            elif len(new) < 8:
                flash("New password must contain at least 8 characters.", "danger")
            elif new != confirm:
                flash("New password and confirmation do not match.", "danger")
            else:
                db.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new), g.user["id"]),
                )
                db.commit()
                flash("Password changed successfully.", "success")
                return redirect(url_for("dashboard"))

        return render_template("change_password.html")

    @app.get("/dashboard")
    @login_required
    def dashboard() -> str:
        db = get_db()
        today = date.today().isoformat()
        counts = {
            "students": db.execute("SELECT COUNT(*) AS c FROM students WHERE active = 1").fetchone()["c"],
            "sessions": db.execute("SELECT COUNT(*) AS c FROM attendance_sessions").fetchone()["c"],
            "today_sessions": db.execute(
                "SELECT COUNT(*) AS c FROM attendance_sessions WHERE attendance_date = ?", (today,)
            ).fetchone()["c"],
            "today_present": db.execute(
                """
                SELECT COUNT(*) AS c
                FROM attendance_records ar
                JOIN attendance_sessions s ON s.id = ar.session_id
                WHERE s.attendance_date = ? AND ar.status = 'present'
                """,
                (today,),
            ).fetchone()["c"],
        }
        recent_sessions = db.execute(
            """
            SELECT s.*, u.full_name AS creator_name,
                   SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS present_count,
                   COUNT(ar.id) AS recorded_count
            FROM attendance_sessions s
            JOIN users u ON u.id = s.created_by
            LEFT JOIN attendance_records ar ON ar.session_id = s.id
            GROUP BY s.id
            ORDER BY s.id DESC
            LIMIT 6
            """
        ).fetchall()
        return render_template("dashboard.html", counts=counts, recent_sessions=recent_sessions)

    @app.get("/users")
    @admin_required
    def users() -> str:
        rows = get_db().execute(
            "SELECT id, username, full_name, role, created_at FROM users ORDER BY full_name"
        ).fetchall()
        return render_template("users.html", users=rows)

    @app.route("/users/new", methods=("GET", "POST"))
    @admin_required
    def user_new() -> Response | str:
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            full_name = request.form.get("full_name", "").strip()
            role = request.form.get("role", "teacher")
            password = request.form.get("password", "")

            error = None
            if not username or not full_name or not password:
                error = "All fields are required."
            elif role not in {"admin", "teacher"}:
                error = "Invalid role."
            elif len(password) < 8:
                error = "Password must contain at least 8 characters."

            if error:
                flash(error, "danger")
            else:
                try:
                    db = get_db()
                    db.execute(
                        "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                        (username, generate_password_hash(password), full_name, role),
                    )
                    db.commit()
                    flash("User account created.", "success")
                    return redirect(url_for("users"))
                except sqlite3.IntegrityError:
                    flash("That username already exists.", "danger")

        return render_template("user_form.html")

    @app.get("/students")
    @login_required
    def students() -> str:
        search = request.args.get("search", "").strip()
        class_name = request.args.get("class_name", "").strip()
        section = request.args.get("section", "").strip().upper()

        sql = "SELECT * FROM students WHERE 1=1"
        params: list[Any] = []
        if search:
            sql += " AND (name LIKE ? OR admission_no LIKE ? OR roll_no LIKE ?)"
            wildcard = f"%{search}%"
            params.extend([wildcard, wildcard, wildcard])
        if class_name:
            sql += " AND class_name = ?"
            params.append(class_name)
        if section:
            sql += " AND section = ?"
            params.append(section)
        sql += " ORDER BY CAST(class_name AS INTEGER), section, CAST(roll_no AS INTEGER), name"

        db = get_db()
        rows = db.execute(sql, params).fetchall()
        classes = db.execute(
            "SELECT DISTINCT class_name, section FROM students ORDER BY class_name, section"
        ).fetchall()
        return render_template(
            "students.html",
            students=rows,
            classes=classes,
            search=search,
            class_name=class_name,
            section=section,
        )

    @app.route("/students/new", methods=("GET", "POST"))
    @admin_required
    def student_new() -> Response | str:
        if request.method == "POST":
            return save_student(None)
        return render_template("student_form.html", student=None)

    @app.route("/students/<int:student_id>/edit", methods=("GET", "POST"))
    @admin_required
    def student_edit(student_id: int) -> Response | str:
        student = get_student_or_404(student_id)
        if request.method == "POST":
            return save_student(student_id)
        return render_template("student_form.html", student=student)

    def save_student(student_id: int | None) -> Response | str:
        admission_no = request.form.get("admission_no", "").strip().upper()
        name = request.form.get("name", "").strip()
        class_name = request.form.get("class_name", "").strip()
        section = request.form.get("section", "").strip().upper()
        roll_no = request.form.get("roll_no", "").strip()
        parent_phone = request.form.get("parent_phone", "").strip()

        if not all([admission_no, name, class_name, section, roll_no]):
            flash("Admission number, name, class, section and roll number are required.", "danger")
            student = get_student_or_404(student_id) if student_id else None
            return render_template("student_form.html", student=student)

        db = get_db()
        try:
            if student_id is None:
                token = "STU-" + secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:16].upper()
                db.execute(
                    """
                    INSERT INTO students
                    (admission_no, name, class_name, section, roll_no, parent_phone, qr_token)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (admission_no, name, class_name, section, roll_no, parent_phone, token),
                )
                message = "Student registered and QR token generated."
            else:
                db.execute(
                    """
                    UPDATE students
                    SET admission_no = ?, name = ?, class_name = ?, section = ?,
                        roll_no = ?, parent_phone = ?
                    WHERE id = ?
                    """,
                    (admission_no, name, class_name, section, roll_no, parent_phone, student_id),
                )
                message = "Student details updated."
            db.commit()
            flash(message, "success")
            return redirect(url_for("students"))
        except sqlite3.IntegrityError as exc:
            if "admission_no" in str(exc):
                flash("Admission number already exists.", "danger")
            else:
                flash("A student with the same class, section and roll number already exists.", "danger")
            student = get_student_or_404(student_id) if student_id else None
            return render_template("student_form.html", student=student)

    @app.post("/students/<int:student_id>/toggle")
    @admin_required
    def student_toggle(student_id: int) -> Response:
        student = get_student_or_404(student_id)
        new_value = 0 if student["active"] else 1
        db = get_db()
        db.execute("UPDATE students SET active = ? WHERE id = ?", (new_value, student_id))
        db.commit()
        flash("Student status updated.", "success")
        return redirect(url_for("students"))

    @app.get("/students/<int:student_id>/card")
    @login_required
    def student_card(student_id: int) -> str:
        student = get_student_or_404(student_id)
        qr_data_uri = make_qr_data_uri(student["qr_token"])
        return render_template("student_card.html", student=student, qr_data_uri=qr_data_uri)

    @app.get("/sessions")
    @login_required
    def sessions_list() -> str:
        rows = get_db().execute(
            """
            SELECT s.*, u.full_name AS creator_name,
                   SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS present_count,
                   SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) AS absent_count
            FROM attendance_sessions s
            JOIN users u ON u.id = s.created_by
            LEFT JOIN attendance_records ar ON ar.session_id = s.id
            GROUP BY s.id
            ORDER BY s.attendance_date DESC, s.id DESC
            """
        ).fetchall()
        return render_template("sessions.html", sessions=rows)

    @app.route("/sessions/new", methods=("GET", "POST"))
    @login_required
    def session_new() -> Response | str:
        db = get_db()
        class_options = db.execute(
            """
            SELECT class_name, section, COUNT(*) AS student_count
            FROM students
            WHERE active = 1
            GROUP BY class_name, section
            ORDER BY class_name, section
            """
        ).fetchall()

        if request.method == "POST":
            class_name = request.form.get("class_name", "").strip()
            section = request.form.get("section", "").strip().upper()
            subject = request.form.get("subject", "").strip()
            period = request.form.get("period", "").strip()
            attendance_date = request.form.get("attendance_date", date.today().isoformat())

            if not all([class_name, section, subject, period, attendance_date]):
                flash("All fields are required.", "danger")
            else:
                try:
                    cursor = db.execute(
                        """
                        INSERT INTO attendance_sessions
                        (class_name, section, subject, period, attendance_date, created_by)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (class_name, section, subject, period, attendance_date, g.user["id"]),
                    )
                    db.commit()
                    flash("Attendance session started.", "success")
                    return redirect(url_for("session_scan", session_id=cursor.lastrowid))
                except sqlite3.IntegrityError:
                    flash("A session already exists for this class, subject, period and date.", "danger")

        return render_template("session_form.html", class_options=class_options, today=date.today().isoformat())

    @app.get("/sessions/<int:session_id>")
    @login_required
    def session_detail(session_id: int) -> str:
        attendance_session = get_session_or_404(session_id)
        db = get_db()
        records = db.execute(
            """
            SELECT ar.*, st.name, st.roll_no, st.admission_no
            FROM attendance_records ar
            JOIN students st ON st.id = ar.student_id
            WHERE ar.session_id = ?
            ORDER BY CAST(st.roll_no AS INTEGER), st.name
            """,
            (session_id,),
        ).fetchall()
        unmarked = db.execute(
            """
            SELECT st.*
            FROM students st
            WHERE st.active = 1 AND st.class_name = ? AND st.section = ?
              AND NOT EXISTS (
                  SELECT 1 FROM attendance_records ar
                  WHERE ar.session_id = ? AND ar.student_id = st.id
              )
            ORDER BY CAST(st.roll_no AS INTEGER), st.name
            """,
            (attendance_session["class_name"], attendance_session["section"], session_id),
        ).fetchall()
        return render_template(
            "session_detail.html",
            attendance_session=attendance_session,
            records=records,
            unmarked=unmarked,
        )

    @app.get("/sessions/<int:session_id>/scan")
    @login_required
    def session_scan(session_id: int) -> str:
        attendance_session = get_session_or_404(session_id)
        if attendance_session["status"] != "open":
            flash("This attendance session is already finalized.", "warning")
            return redirect(url_for("session_detail", session_id=session_id))
        return render_template("scanner.html", attendance_session=attendance_session)

    @app.post("/api/sessions/<int:session_id>/scan")
    @login_required
    def api_session_scan(session_id: int) -> tuple[Response, int]:
        data = request.get_json(silent=True) or {}
        token = str(data.get("token", "")).strip()
        payload, status_code = mark_attendance_from_token(session_id, token)
        return jsonify(payload), status_code

    @app.post("/api/sessions/<int:session_id>/scan-image")
    @login_required
    def api_session_scan_image(session_id: int) -> tuple[Response, int]:
        image_file = request.files.get("image")
        if image_file is None or not image_file.filename:
            return jsonify(ok=False, no_qr=True, message="No image was received."), 400

        try:
            import cv2
            import numpy as np

            image_bytes = image_file.read()
            image_array = np.frombuffer(image_bytes, dtype=np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            if image is None:
                return jsonify(ok=False, no_qr=True, message="The image could not be read."), 400

            token, points, _ = cv2.QRCodeDetector().detectAndDecode(image)
        except Exception:
            return jsonify(ok=False, no_qr=True, message="QR decoding failed."), 422

        token = token.strip()
        if not token or points is None:
            return jsonify(ok=False, no_qr=True, message="No QR code was found."), 422

        payload, status_code = mark_attendance_from_token(session_id, token)
        payload["decoded_token"] = token
        return jsonify(payload), status_code

    @app.post("/sessions/<int:session_id>/manual")
    @login_required
    def session_manual(session_id: int) -> Response:
        attendance_session = get_session_or_404(session_id)
        if attendance_session["status"] != "open":
            flash("Closed sessions cannot be changed.", "danger")
            return redirect(url_for("session_detail", session_id=session_id))

        try:
            student_id = int(request.form.get("student_id", ""))
        except (TypeError, ValueError):
            abort(400)
        status = request.form.get("status", "present")
        if status not in {"present", "absent"}:
            abort(400)

        student = get_student_or_404(student_id)
        if student["class_name"] != attendance_session["class_name"] or student["section"] != attendance_session["section"]:
            abort(400)

        db = get_db()
        db.execute(
            """
            INSERT INTO attendance_records
            (session_id, student_id, status, marked_by, method)
            VALUES (?, ?, ?, ?, 'manual')
            ON CONFLICT(session_id, student_id)
            DO UPDATE SET status = excluded.status,
                          marked_at = CURRENT_TIMESTAMP,
                          marked_by = excluded.marked_by,
                          method = 'manual'
            """,
            (session_id, student_id, status, g.user["id"]),
        )
        db.commit()
        flash(f"{student['name']} marked {status}.", "success")
        return redirect(url_for("session_detail", session_id=session_id))

    @app.post("/sessions/<int:session_id>/finalize")
    @login_required
    def session_finalize(session_id: int) -> Response:
        attendance_session = get_session_or_404(session_id)
        if attendance_session["status"] != "open":
            flash("Session is already finalized.", "warning")
            return redirect(url_for("session_detail", session_id=session_id))

        db = get_db()
        db.execute(
            """
            INSERT INTO attendance_records
            (session_id, student_id, status, marked_by, method)
            SELECT ?, st.id, 'absent', ?, 'finalize'
            FROM students st
            WHERE st.active = 1 AND st.class_name = ? AND st.section = ?
              AND NOT EXISTS (
                  SELECT 1 FROM attendance_records ar
                  WHERE ar.session_id = ? AND ar.student_id = st.id
              )
            """,
            (
                session_id,
                g.user["id"],
                attendance_session["class_name"],
                attendance_session["section"],
                session_id,
            ),
        )
        db.execute(
            "UPDATE attendance_sessions SET status = 'closed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        db.commit()
        flash("Session finalized. All unmarked students were marked absent.", "success")
        return redirect(url_for("session_detail", session_id=session_id))

    @app.get("/reports")
    @login_required
    def reports() -> str:
        from_date = request.args.get("from_date", date.today().replace(day=1).isoformat())
        to_date = request.args.get("to_date", date.today().isoformat())
        class_name = request.args.get("class_name", "").strip()
        section = request.args.get("section", "").strip().upper()

        sql = """
            SELECT st.id, st.admission_no, st.name, st.class_name, st.section, st.roll_no,
                   SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS present_count,
                   SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) AS absent_count,
                   COUNT(ar.id) AS total_records
            FROM students st
            JOIN attendance_records ar ON ar.student_id = st.id
            JOIN attendance_sessions s ON s.id = ar.session_id
            WHERE s.attendance_date BETWEEN ? AND ?
        """
        params: list[Any] = [from_date, to_date]
        if class_name:
            sql += " AND st.class_name = ?"
            params.append(class_name)
        if section:
            sql += " AND st.section = ?"
            params.append(section)
        sql += " GROUP BY st.id ORDER BY st.class_name, st.section, CAST(st.roll_no AS INTEGER), st.name"

        db = get_db()
        rows = db.execute(sql, params).fetchall()
        classes = db.execute(
            "SELECT DISTINCT class_name, section FROM students ORDER BY class_name, section"
        ).fetchall()
        return render_template(
            "reports.html",
            rows=rows,
            classes=classes,
            from_date=from_date,
            to_date=to_date,
            class_name=class_name,
            section=section,
        )

    @app.get("/reports/export.csv")
    @login_required
    def report_export() -> Response:
        from_date = request.args.get("from_date", date.today().replace(day=1).isoformat())
        to_date = request.args.get("to_date", date.today().isoformat())
        class_name = request.args.get("class_name", "").strip()
        section = request.args.get("section", "").strip().upper()

        sql = """
            SELECT st.admission_no, st.name, st.class_name, st.section, st.roll_no,
                   SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) AS present_count,
                   SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) AS absent_count,
                   COUNT(ar.id) AS total_records
            FROM students st
            JOIN attendance_records ar ON ar.student_id = st.id
            JOIN attendance_sessions s ON s.id = ar.session_id
            WHERE s.attendance_date BETWEEN ? AND ?
        """
        params: list[Any] = [from_date, to_date]
        if class_name:
            sql += " AND st.class_name = ?"
            params.append(class_name)
        if section:
            sql += " AND st.section = ?"
            params.append(section)
        sql += " GROUP BY st.id ORDER BY st.class_name, st.section, CAST(st.roll_no AS INTEGER), st.name"

        rows = get_db().execute(sql, params).fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Admission No", "Student Name", "Class", "Section", "Roll No",
            "Present", "Absent", "Total", "Attendance Percentage"
        ])
        for row in rows:
            percentage = round((row["present_count"] / row["total_records"] * 100), 2) if row["total_records"] else 0
            writer.writerow([
                row["admission_no"], row["name"], row["class_name"], row["section"], row["roll_no"],
                row["present_count"], row["absent_count"], row["total_records"], percentage
            ])

        filename = f"attendance_{from_date}_to_{to_date}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.errorhandler(403)
    def forbidden(_: Exception) -> tuple[str, int]:
        return render_template("error.html", code=403, message="You do not have permission to open this page."), 403

    @app.errorhandler(404)
    def not_found(_: Exception) -> tuple[str, int]:
        return render_template("error.html", code=404, message="The requested page was not found."), 404


def get_student_or_404(student_id: int | None) -> sqlite3.Row:
    if student_id is None:
        abort(404)
    student = get_db().execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if student is None:
        abort(404)
    return student


def get_session_or_404(session_id: int) -> sqlite3.Row:
    row = get_db().execute(
        """
        SELECT s.*, u.full_name AS creator_name
        FROM attendance_sessions s
        JOIN users u ON u.id = s.created_by
        WHERE s.id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        abort(404)
    return row



def mark_attendance_from_token(session_id: int, token: str) -> tuple[dict[str, Any], int]:
    token = token.strip().upper()
    attendance_session = get_session_or_404(session_id)
    if attendance_session["status"] != "open":
        return {"ok": False, "message": "Attendance session is closed."}, 409
    if not token:
        return {"ok": False, "message": "QR token is missing."}, 400

    db = get_db()
    student = db.execute(
        "SELECT * FROM students WHERE qr_token = ? AND active = 1", (token,)
    ).fetchone()
    if student is None:
        return {"ok": False, "message": "Invalid or inactive student QR code."}, 404
    if (
        student["class_name"] != attendance_session["class_name"]
        or student["section"] != attendance_session["section"]
    ):
        return {
            "ok": False,
            "message": (
                f"{student['name']} belongs to Class "
                f"{student['class_name']}-{student['section']}, not this session."
            ),
            "student": student_to_json(student),
        }, 409

    try:
        db.execute(
            """
            INSERT INTO attendance_records
            (session_id, student_id, status, marked_by, method)
            VALUES (?, ?, 'present', ?, 'qr')
            """,
            (session_id, student["id"], g.user["id"]),
        )
        db.commit()
    except sqlite3.IntegrityError:
        existing = db.execute(
            "SELECT status FROM attendance_records WHERE session_id = ? AND student_id = ?",
            (session_id, student["id"]),
        ).fetchone()
        return {
            "ok": False,
            "duplicate": True,
            "message": f"{student['name']} is already marked {existing['status']}.",
            "student": student_to_json(student),
        }, 409

    return {
        "ok": True,
        "message": f"Attendance marked for {student['name']}.",
        "student": student_to_json(student),
    }, 200

def make_qr_data_uri(token: str) -> str:
    image = qrcode.make(token)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def student_to_json(student: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": student["id"],
        "admission_no": student["admission_no"],
        "name": student["name"],
        "class_name": student["class_name"],
        "section": student["section"],
        "roll_no": student["roll_no"],
    }


app = create_app()

if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host="127.0.0.1",
        port=5000,
    )
