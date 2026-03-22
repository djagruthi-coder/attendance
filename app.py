from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3

# Create Flask app and allow cross-origin requests (CORS).
app = Flask(__name__)
CORS(app)

DB_FILE = "attendance.db"
SUBJECTS = ["Math", "Physics", "Chemistry", "English", "Computer Science"]


def get_db_connection():
    """Open a SQLite connection with row access by column name."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Create/migrate students table and seed data safely.
    - Students: 24NN1A0501 to 24NN1A0530 (role=student)
    - Teacher: teacher1 (role=teacher)
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Create table (role included for fresh databases).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            roll_no TEXT PRIMARY KEY,
            dob TEXT NOT NULL,
            attended INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            role TEXT NOT NULL DEFAULT 'student'
        )
        """
    )

    # If DB existed before role was introduced, add role column.
    columns = cur.execute("PRAGMA table_info(students)").fetchall()
    column_names = [col["name"] for col in columns]
    if "role" not in column_names:
        cur.execute("ALTER TABLE students ADD COLUMN role TEXT NOT NULL DEFAULT 'student'")

    # Ensure all existing non-teacher users are marked as student.
    cur.execute("UPDATE students SET role = 'student' WHERE role IS NULL OR role = ''")

    # Insert students one by one with INSERT OR IGNORE (prevents duplicates).
    for i in range(1, 31):
        roll_no = f"24NN1A05{str(i).zfill(2)}"
        day = (i % 28) + 1
        dob = f"2006-01-{str(day).zfill(2)}"
        cur.execute(
            """
            INSERT OR IGNORE INTO students (roll_no, dob, attended, total, role)
            VALUES (?, ?, 0, 0, 'student')
            """,
            (roll_no, dob),
        )
        # Force role to stay student for these 30 user accounts.
        cur.execute("UPDATE students SET role = 'student' WHERE roll_no = ?", (roll_no,))

    # Add (or correct) teacher account.
    cur.execute(
        """
        INSERT OR IGNORE INTO students (roll_no, dob, attended, total, role)
        VALUES (?, ?, 0, 0, 'teacher')
        """,
        ("teacher1", "2000-01-01"),
    )
    cur.execute(
        "UPDATE students SET dob = ?, role = 'teacher' WHERE roll_no = ?",
        ("2000-01-01", "teacher1"),
    )

    # New subject-wise attendance table.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL,
            subject TEXT NOT NULL,
            attended INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            UNIQUE(roll_no, subject)
        )
        """
    )

    # Ensure each student has one record for each subject.
    student_rows = cur.execute(
        "SELECT roll_no FROM students WHERE role = 'student' ORDER BY roll_no"
    ).fetchall()
    for row in student_rows:
        for subject in SUBJECTS:
            cur.execute(
                """
                INSERT OR IGNORE INTO attendance_records (roll_no, subject, attended, total)
                VALUES (?, ?, 0, 0)
                """,
                (row["roll_no"], subject),
            )

    conn.commit()
    conn.close()


def calculate_alert(attended, total):
    """Return percentage + alert level + readable message."""
    percentage = (attended / total * 100) if total > 0 else 0.0

    if percentage < 75:
        alert = "Critical"
        message = "Critical: You are below minimum attendance requirement!"
    elif percentage < 85:
        alert = "Warning"
        message = "Warning: Your attendance is below 85%. You may fall below required attendance if not improved."
    else:
        alert = "Safe"
        message = "Safe: Your attendance is good"

    return round(percentage, 2), alert, message


def attendance_response(attended, total):
    """Build standard attendance JSON payload."""
    percentage, alert, message = calculate_alert(attended, total)
    return {
        "percentage": percentage,
        "alert": alert,
        "message": message,
        "attended": attended,
        "total": total,
    }


def get_user(conn, roll_no):
    """Fetch user by roll number."""
    return conn.execute(
        "SELECT roll_no, role FROM students WHERE roll_no = ?",
        (roll_no,),
    ).fetchone()


def get_subject_rows(conn, roll_no):
    """Fetch subject-wise attendance rows for a student."""
    return conn.execute(
        """
        SELECT subject, attended, total
        FROM attendance_records
        WHERE roll_no = ?
        ORDER BY subject
        """,
        (roll_no,),
    ).fetchall()


def build_student_dashboard(conn, roll_no):
    """Return subject-wise rows + overall stats for one student."""
    rows = get_subject_rows(conn, roll_no)
    subject_wise = []
    total_attended = 0
    total_classes = 0

    for row in rows:
        row_attended = row["attended"]
        row_total = row["total"]
        total_attended += row_attended
        total_classes += row_total
        percentage, _, _ = calculate_alert(row_attended, row_total)
        subject_wise.append(
            {
                "subject": row["subject"],
                "attended": row_attended,
                "total": row_total,
                "percentage": percentage,
            }
        )

    overall = attendance_response(total_attended, total_classes)
    return {
        "roll_no": roll_no,
        "subject_wise": subject_wise,
        "overall": overall,
    }


@app.route("/")
def home():
    """Serve the simple frontend page."""
    return send_from_directory(".", "index.html")


@app.route("/login", methods=["POST"])
def login():
    """
    Login with roll_no and dob.
    Request JSON: { "roll_no": "...", "dob": "YYYY-MM-DD" }
    """
    data = request.get_json(silent=True) or {}
    roll_no = data.get("roll_no", "").strip()
    dob = data.get("dob", "").strip()

    if not roll_no or not dob:
        return jsonify({"success": False, "message": "roll_no and dob are required."}), 400

    conn = get_db_connection()
    user = conn.execute(
        "SELECT roll_no, dob, role FROM students WHERE roll_no = ? AND dob = ?",
        (roll_no, dob),
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({"success": False, "message": "Invalid roll number or date of birth."}), 401

    return jsonify(
        {
            "success": True,
            "message": "Login successful.",
            "role": user["role"],
            "roll_no": user["roll_no"],
        }
    )


@app.route("/students", methods=["POST"])
def list_students():
    """
    Teacher-only endpoint to fetch all student roll numbers.
    Request JSON:
      { "actor_roll_no": "teacher1" }
    """
    data = request.get_json(silent=True) or {}
    actor_roll_no = data.get("actor_roll_no", "").strip()
    if not actor_roll_no:
        return jsonify({"message": "actor_roll_no is required."}), 400

    conn = get_db_connection()
    actor = conn.execute(
        "SELECT roll_no, role FROM students WHERE roll_no = ?",
        (actor_roll_no,),
    ).fetchone()
    if not actor or actor["role"] != "teacher":
        conn.close()
        return jsonify({"message": "Only teachers can view student list."}), 403

    rows = conn.execute("SELECT roll_no FROM students WHERE role = 'student' ORDER BY roll_no").fetchall()
    conn.close()
    return jsonify({"students": [row["roll_no"] for row in rows]})


@app.route("/bulk_attendance_subject", methods=["POST"])
def bulk_attendance_subject():
    """
    Teacher marks attendance for many students in one request for one subject.
    Request JSON:
      {
        "actor_roll_no": "teacher1",
        "subject": "Math",
        "records": [
          { "roll_no": "24NN1A0501", "present": true },
          { "roll_no": "24NN1A0502", "present": false }
        ]
      }
    """
    data = request.get_json(silent=True) or {}
    actor_roll_no = data.get("actor_roll_no", "").strip()
    subject = data.get("subject", "").strip()
    records = data.get("records", [])

    if (
        not actor_roll_no
        or not subject
        or subject not in SUBJECTS
        or not isinstance(records, list)
        or not records
    ):
        return jsonify({"message": "actor_roll_no, valid subject, and non-empty records are required."}), 400

    conn = get_db_connection()
    actor = get_user(conn, actor_roll_no)
    if not actor or actor["role"] != "teacher":
        conn.close()
        return jsonify({"message": "Only teachers can update attendance."}), 403

    updated = []
    skipped = []

    for item in records:
        roll_no = str(item.get("roll_no", "")).strip()
        present = bool(item.get("present", False))

        if not roll_no:
            continue

        student = conn.execute("SELECT roll_no, role FROM students WHERE roll_no = ?", (roll_no,)).fetchone()
        if not student or student["role"] != "student":
            skipped.append(roll_no)
            continue

        row = conn.execute(
            """
            SELECT attended, total
            FROM attendance_records
            WHERE roll_no = ? AND subject = ?
            """,
            (roll_no, subject),
        ).fetchone()
        if not row:
            skipped.append(roll_no)
            continue

        attended = row["attended"] + (1 if present else 0)
        total = row["total"] + 1
        conn.execute(
            """
            UPDATE attendance_records
            SET attended = ?, total = ?
            WHERE roll_no = ? AND subject = ?
            """,
            (attended, total, roll_no, subject),
        )
        updated.append(
            {
                "roll_no": roll_no,
                "subject": subject,
                **attendance_response(attended, total),
            }
        )

    conn.commit()
    conn.close()

    return jsonify(
        {
            "message": "Subject-wise bulk attendance submitted.",
            "subject": subject,
            "updated_count": len(updated),
            "skipped_count": len(skipped),
            "updated": updated,
            "skipped": skipped,
        }
    )


@app.route("/get_attendance", methods=["POST"])
def get_attendance():
    """
    Strict role-based attendance view.
    Request JSON:
      {
        "actor_roll_no": "24NN1A0501 or teacher1",
        "roll_no": "24NN1A0501"
      }
    """
    data = request.get_json(silent=True) or {}
    actor_roll_no = data.get("actor_roll_no", "").strip()
    roll_no = data.get("roll_no", "").strip()

    if not actor_roll_no or not roll_no:
        return jsonify({"message": "actor_roll_no and roll_no are required."}), 400

    conn = get_db_connection()
    actor = get_user(conn, actor_roll_no)
    student = get_user(conn, roll_no)

    if not actor:
        conn.close()
        return jsonify({"message": "Invalid actor user."}), 401
    if not student:
        conn.close()
        return jsonify({"message": "Student not found."}), 404
    if student["role"] != "student":
        conn.close()
        return jsonify({"message": "Attendance view is available for student accounts only."}), 400
    # Student can view only self. Teacher can view anyone.
    if actor["role"] == "student" and actor_roll_no != roll_no:
        conn.close()
        return jsonify({"message": "Students can only view their own attendance."}), 403
    if actor["role"] not in ("student", "teacher"):
        conn.close()
        return jsonify({"message": "Invalid role."}), 403

    dashboard = build_student_dashboard(conn, roll_no)
    conn.close()
    return jsonify(dashboard)


@app.route("/teacher_all_attendance", methods=["POST"])
def teacher_all_attendance():
    """
    Teacher-only read-only view of all students with overall attendance.
    Request JSON:
      { "actor_roll_no": "teacher1" }
    """
    data = request.get_json(silent=True) or {}
    actor_roll_no = data.get("actor_roll_no", "").strip()
    if not actor_roll_no:
        return jsonify({"message": "actor_roll_no is required."}), 400

    conn = get_db_connection()
    actor = get_user(conn, actor_roll_no)
    if not actor or actor["role"] != "teacher":
        conn.close()
        return jsonify({"message": "Only teachers can view all attendance."}), 403

    students = conn.execute("SELECT roll_no FROM students WHERE role = 'student' ORDER BY roll_no").fetchall()
    all_rows = []
    for row in students:
        dashboard = build_student_dashboard(conn, row["roll_no"])
        all_rows.append(
            {
                "roll_no": row["roll_no"],
                "percentage": dashboard["overall"]["percentage"],
                "alert": dashboard["overall"]["alert"],
                "attended": dashboard["overall"]["attended"],
                "total": dashboard["overall"]["total"],
            }
        )

    conn.close()
    return jsonify({"students": all_rows})


if __name__ == "__main__":
    # Initialize DB before starting server.
    init_db()
    app.run(debug=True)
