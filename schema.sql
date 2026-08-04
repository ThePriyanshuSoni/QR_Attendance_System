CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'teacher')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admission_no TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    class_name TEXT NOT NULL,
    section TEXT NOT NULL,
    roll_no TEXT NOT NULL,
    parent_phone TEXT,
    qr_token TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (class_name, section, roll_no)
);

CREATE TABLE IF NOT EXISTS attendance_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT NOT NULL,
    section TEXT NOT NULL,
    subject TEXT NOT NULL,
    period TEXT NOT NULL,
    attendance_date TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_by INTEGER NOT NULL,
    FOREIGN KEY (created_by) REFERENCES users(id),
    UNIQUE (class_name, section, subject, period, attendance_date)
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('present', 'absent')),
    marked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    marked_by INTEGER NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('qr', 'manual', 'finalize')),
    remarks TEXT,
    FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (marked_by) REFERENCES users(id),
    UNIQUE (session_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_students_class ON students(class_name, section);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON attendance_sessions(attendance_date);
CREATE INDEX IF NOT EXISTS idx_records_session ON attendance_records(session_id);
