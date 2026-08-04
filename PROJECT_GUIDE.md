# Beginner Development Guide

## How the system works

1. The administrator registers a student.
2. The server generates a random QR token and stores it in SQLite.
3. The QR-card page converts that token into a QR image.
4. A teacher creates an attendance session for one class, subject, period and date.
5. JavaScript captures a camera frame or selected image.
6. Flask uses OpenCV to decode the QR token from the image.
7. Flask checks whether the token is valid and belongs to the selected class.
8. SQLite's unique constraint rejects duplicate records.
9. Finalization marks every unrecorded active student absent.
10. The report query calculates present, absent and total records.

## Main code locations

- Login: `app.py`, route `/login`
- Add student: `app.py`, route `/students/new`
- Generate QR image: `make_qr_data_uri()`
- Create session: route `/sessions/new`
- Scan API: route `/api/sessions/<session_id>/scan`
- Duplicate prevention: `UNIQUE (session_id, student_id)` in `schema.sql`
- Finalization: route `/sessions/<session_id>/finalize`
- Reports: routes `/reports` and `/reports/export.csv`
- Camera JavaScript: `templates/scanner.html`

## Recommended learning order

1. Learn basic HTML forms and links.
2. Learn Python variables, functions, conditions and lists.
3. Learn Flask routes, `request.form`, templates and redirects.
4. Learn simple SQL: `SELECT`, `INSERT`, `UPDATE` and `JOIN`.
5. Trace one feature from browser form to Flask route to database.
6. Run tests and deliberately test invalid QR codes and duplicates.

## Viva questions to prepare

- Why was QR selected instead of face recognition or RFID?
- Why is SQLite suitable for this mini project?
- How are duplicate attendance records prevented?
- Why should personal details not be stored inside the QR code?
- What happens when a student from another class is scanned?
- What is the difference between an attendance session and an attendance record?
- Why is teacher verification still needed with QR cards?
- What would need to change for a cloud or multi-school deployment?
