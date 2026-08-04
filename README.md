# QR-Based Attendance System for Rural Schools

A beginner-friendly BCA mini project built with Python Flask and SQLite. It runs on a school laptop, stores data locally, generates student QR cards, scans QR codes, prevents duplicate attendance, finalizes absentees, and exports reports to CSV.

## Features

- Administrator and teacher login
- Student registration and editing
- Unique QR attendance card for every student
- Class/section attendance sessions
- Camera and QR-image scanning decoded by OpenCV on the local Flask server
- QR-image scanning and manual-token fallback
- Duplicate scan prevention
- Wrong-class validation
- Manual present/absent correction
- Automatic absent marking when a session is finalized
- Date-range attendance reports and CSV export
- Local SQLite storage; internet is not required after installation

## Technology

- Python 3.10 or newer
- Flask
- SQLite
- HTML, CSS and JavaScript
- Python `qrcode` package
- OpenCV `QRCodeDetector` for scanning

## Windows setup

1. Install Python from python.org. During installation, select **Add Python to PATH**.
2. Extract this project ZIP.
3. Double-click `setup_windows.bat` once.
4. Double-click `run_windows.bat` whenever you want to start the project.
5. Open `http://127.0.0.1:5000` in current Chrome or Edge.

## Manual setup

```bash
python -m venv .venv
```

Activate the environment:

```bash
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

Install packages and run:

```bash
python -m pip install -r requirements.txt
python seed_demo.py
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Demo logins

```text
Administrator
Username: admin
Password: admin123

Teacher
Username: teacher
Password: teacher123
```

Change these passwords from the **Password** page before a real demonstration.

## First demonstration

1. Log in as `admin`.
2. Open **Students**.
3. Add students, or run `python seed_demo.py` to add six demo students.
4. Open a student's **QR card** and print it or display it on another screen.
5. Open **Attendance → New session**.
6. Select Class 6-A, enter subject and period, then create the session.
7. Select **Start camera** and scan the QR card.
8. Scan the same card again to demonstrate duplicate prevention.
9. Open **Review attendance** and finalize the session.
10. Open **Reports** and export CSV.

## Camera notes

- Use a recent Chrome, Edge or Firefox browser.
- Camera permission is normally available on `http://localhost` or `http://127.0.0.1`.
- A phone opening the laptop's plain HTTP LAN address may block camera access. For the easiest classroom demo, use the laptop webcam on localhost.
- When camera scanning is unavailable, use **Scan image** or enter the printed QR token manually.

## Project structure

```text
qr_attendance_system/
├── app.py                 Flask routes and business logic
├── schema.sql             SQLite database structure
├── seed_demo.py           Adds demo students
├── requirements.txt       Python dependencies
├── templates/             HTML pages
├── static/css/style.css   Offline responsive design
├── tests/test_app.py      Automated tests
└── instance/              Database created at runtime
```

## Database tables

- `users`
- `students`
- `attendance_sessions`
- `attendance_records`

A unique database constraint on `(session_id, student_id)` prevents duplicate attendance records.

## Testing

```bash
pytest -q
```

## Limits of this mini project

- QR cards can be exchanged between students, so a teacher should verify the student's identity after scanning.
- This version runs on one local computer. Cloud synchronization and SMS alerts are future enhancements.
- The default Flask development server is suitable for college demonstration, not public production deployment.
