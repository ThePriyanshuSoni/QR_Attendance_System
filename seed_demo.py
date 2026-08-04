from app import create_app, get_db

SAMPLE_STUDENTS = [
    ("MPEC001", "Aarav Kumar", "6", "A", "1", "9000000001", "STU-DEMO-0001"),
    ("MPEC002", "Ananya Singh", "6", "A", "2", "9000000002", "STU-DEMO-0002"),
    ("MPEC003", "Deepak Yadav", "6", "A", "3", "9000000003", "STU-DEMO-0003"),
    ("MPEC004", "Kavya Verma", "6", "A", "4", "9000000004", "STU-DEMO-0004"),
    ("MPEC005", "Rohan Pal", "6", "A", "5", "9000000005", "STU-DEMO-0005"),
    ("MPEC006", "Nisha Bakshi", "6", "A", "6", "9000000006", "STU-DEMO-0006"),
]

app = create_app()
with app.app_context():
    db = get_db()
    db.executemany(
        """
        INSERT OR IGNORE INTO students
        (admission_no, name, class_name, section, roll_no, parent_phone, qr_token)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        SAMPLE_STUDENTS,
    )
    db.commit()
    print("Demo students added. Open Students to print their QR cards.")
