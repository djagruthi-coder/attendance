from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import time
import smtplib
import ssl
from email.mime.text import MIMEText

# Create Flask app and allow cross-origin requests (CORS).
app = Flask(__name__)
CORS(app)

DB_FILE = "attendance.db"
SUBJECTS = ["Math", "Physics", "Chemistry", "English", "Computer Science"]
BRANCHES = ["CSE", "ECE"]
SECTIONS = ["A", "B"]
EMAIL_WARNING_THRESHOLD = 80.0
EMAIL_COOLDOWN_SECONDS = 24 * 60 * 60  # avoid spamming on refresh

# Demo student names for roll_no 24NN1A0501..24NN1A0530
STUDENT_NAMES = [
    "Jagruthi Dasari",
    "Akshara Reddy",
    "Harsha Kumar",
    "Meghana N",
    "Nikhil S",
    "Ananya Patel",
    "Sai Teja",
    "Keerthana S",
    "Vamsi Krishna",
    "Rithika Rao",
    "Srikanth Reddy",
    "Lakshmi Priya",
    "Rahul Varma",
    "Nandini Singh",
    "Karthikeya",
    "Divya Chandra",
    "Arjun Mehta",
    "Swetha Kumar",
    "Rahul Jain",
    "Anusha Thomas",
    "Pranav G",
    "Meera Iyer",
    "Siddharth Rao",
    "Rohan Verma",
    "Pooja Sharma",
    "Mohan Raj",
    "Sana Begum",
    "Tanishq Gupta",
    "Aditi Kulkarni",
    "Kabir Das",
]

TEACHER_ROLL_NO = "teacher1"
TEACHER_DOB = "2000-01-01"
TEACHER_NAME = "College Teacher"
TEACHER_BRANCH = "N/A"
TEACHER_SECTION = "N/A"

# In-memory cooldown cache (simple simulation; resets if server restarts).
last_email_sent_ts_by_roll = {}


def send_email(to_email: str, student_name: str, percentage: float):
    """
    Send warning email using Gmail SMTP.

    Environment variables to set:
      - GMAIL_SMTP_USER (your Gmail address)
      - GMAIL_SMTP_PASSWORD (Gmail App Password)
    """
    smtp_user = os.environ.get("GMAIL_SMTP_USER", "").strip()
    smtp_password = os.environ.get("GMAIL_SMTP_PASSWORD", "").strip()
    smtp_from = smtp_user

    if not smtp_user or not smtp_password or not smtp_from:
        # Required exact fallback message for demo/debug.
        print("Email not configured. Skipping email send.")
        return {"ok": False, "reason": "email_not_configured"}

    subject = "Attendance Warning ⚠️"
    body = (
        f"Hello {student_name},\n\n"
        f"Your attendance is currently {percentage:.2f}%.\n\n"
        "This is below the required threshold.\n"
        "Please attend upcoming classes to avoid shortage.\n\n"
        "Regards,\n"
        "College Attendance System"
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(smtp_user, smtp_password)
        server.sendmail(smtp_from, [to_email], msg.as_string())
        return {"ok": True}
    except Exception as e:
        print(f"Email not sent due to error: {e}")
        return {"ok": False, "reason": str(e)}


def assign_class(i):
    """
    Assign branch+section based on index i (1..30).
    - 1..8   => CSE-A
    - 9..16  => CSE-B
    - 17..23 => ECE-A
    - 24..30 => ECE-B
    """
    if 1 <= i <= 8:
        return "CSE", "A"
    if 9 <= i <= 16:
        return "CSE", "B"
    if 17 <= i <= 23:
        return "ECE", "A"
    return "ECE", "B"


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

    # Create table (role + identity fields for fresh databases).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            roll_no TEXT PRIMARY KEY,
            dob TEXT NOT NULL,
            attended INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            role TEXT NOT NULL DEFAULT 'student',
            name TEXT NOT NULL DEFAULT '',
            branch TEXT NOT NULL DEFAULT '',
            section TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT ''
        )
        """
    )

    # Migrate missing columns for existing DBs.
    columns = cur.execute("PRAGMA table_info(students)").fetchall()
    column_names = [col["name"] for col in columns]

    if "role" not in column_names:
        cur.execute("ALTER TABLE students ADD COLUMN role TEXT NOT NULL DEFAULT 'student'")
    if "name" not in column_names:
        cur.execute("ALTER TABLE students ADD COLUMN name TEXT NOT NULL DEFAULT ''")
    if "branch" not in column_names:
        cur.execute("ALTER TABLE students ADD COLUMN branch TEXT NOT NULL DEFAULT ''")
    if "section" not in column_names:
        cur.execute("ALTER TABLE students ADD COLUMN section TEXT NOT NULL DEFAULT ''")
    if "email" not in column_names:
        cur.execute("ALTER TABLE students ADD COLUMN email TEXT NOT NULL DEFAULT ''")

    # Ensure existing non-teacher accounts stay as students.
    cur.execute("UPDATE students SET role = 'student' WHERE role IS NULL OR role = ''")

    # Seed 30 students with real identity data.
    for i in range(1, 31):
        roll_no = f"24NN1A05{str(i).zfill(2)}"
        day = (i % 28) + 1
        dob = f"2006-01-{str(day).zfill(2)}"
        name = STUDENT_NAMES[i - 1]
        branch, section = assign_class(i)
        email = f"{roll_no}@example.com"

        cur.execute(
            """
            INSERT OR IGNORE INTO students (roll_no, dob, attended, total, role, name, branch, section, email)
            VALUES (?, ?, 0, 0, 'student', ?, ?, ?, ?)
            """,
            (roll_no, dob, name, branch, section, email),
        )
        # Always refresh identity fields for the 30 known students.
        cur.execute(
            """
            UPDATE students
            SET dob = ?, role = 'student', name = ?, branch = ?, section = ?, email = ?
            WHERE roll_no = ?
            """,
            (dob, name, branch, section, email, roll_no),
        )

    # Add (or correct) teacher account.
    cur.execute(
        """
        INSERT OR IGNORE INTO students (roll_no, dob, attended, total, role, name, branch, section, email)
        VALUES (?, ?, 0, 0, 'teacher', ?, ?, ?, ?)
        """,
        (TEACHER_ROLL_NO, TEACHER_DOB, TEACHER_NAME, TEACHER_BRANCH, TEACHER_SECTION, ""),
    )
    cur.execute(
        """
        UPDATE students
        SET dob = ?, role = 'teacher', name = ?, branch = ?, section = ?, email = ?
        WHERE roll_no = ?
        """,
        (TEACHER_DOB, TEACHER_NAME, TEACHER_BRANCH, TEACHER_SECTION, "", TEACHER_ROLL_NO),
    )

    # Subject-wise attendance table (per class).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL,
            subject TEXT NOT NULL,
            attended INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            branch TEXT NOT NULL DEFAULT '',
            section TEXT NOT NULL DEFAULT '',
            UNIQUE(roll_no, subject)
        )
        """
    )

    # Migrate missing branch/section columns for existing attendance_records tables.
    ar_columns = cur.execute("PRAGMA table_info(attendance_records)").fetchall()
    ar_names = [col["name"] for col in ar_columns]
    if "branch" not in ar_names:
        cur.execute("ALTER TABLE attendance_records ADD COLUMN branch TEXT NOT NULL DEFAULT ''")
    if "section" not in ar_names:
        cur.execute("ALTER TABLE attendance_records ADD COLUMN section TEXT NOT NULL DEFAULT ''")

    # Ensure each student has one record for each subject.
    student_rows = cur.execute("SELECT roll_no FROM students WHERE role = 'student' ORDER BY roll_no").fetchall()
    for row in student_rows:
        for subject in SUBJECTS:
            cur.execute(
                """
                INSERT OR IGNORE INTO attendance_records (roll_no, subject, attended, total, branch, section)
                VALUES (?, ?, 0, 0, '', '')
                """,
                (row["roll_no"], subject),
            )

    # Backfill branch/section in attendance_records from students table.
    cur.execute(
        """
        UPDATE attendance_records
        SET branch = (
            SELECT branch FROM students s WHERE s.roll_no = attendance_records.roll_no
        ),
        section = (
            SELECT section FROM students s WHERE s.roll_no = attendance_records.roll_no
        )
        WHERE roll_no IN (SELECT roll_no FROM students WHERE role = 'student')
        """
    )

    conn.commit()
    conn.close()


def calculate_alert(attended, total):
    """Return percentage + alert level + readable message."""
    percentage = (attended / total * 100) if total > 0 else 0.0

    if percentage < 75:
        alert = "Critical"
        message = "Critical: Below minimum attendance!"
    elif percentage < 85:
        alert = "Warning"
        message = "Warning: You may fall below required attendance."
    else:
        alert = "Safe"
        message = "Safe: Attendance is good"

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
        "SELECT roll_no, role, name, branch, section, email FROM students WHERE roll_no = ?",
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
    student = conn.execute(
        "SELECT name, branch, section FROM students WHERE roll_no = ?",
        (roll_no,),
    ).fetchone()

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
    class_str = f"{student['branch']}-{student['section']}" if student else ""

    return {
        "roll_no": roll_no,
        "welcome": {
            "name": student["name"] if student else "",
            "class_str": class_str,
        },
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
        "SELECT roll_no, dob, role, name, branch, section FROM students WHERE roll_no = ? AND dob = ?",
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
            "name": user["name"],
            "branch": user["branch"],
            "section": user["section"],
        }
    )


@app.route("/students", methods=["POST"])
def list_students():
    """
    Teacher-only endpoint to fetch students for one class.
    Request JSON:
      { "actor_roll_no": "teacher1", "branch": "CSE", "section": "A" }
    """
    data = request.get_json(silent=True) or {}
    actor_roll_no = data.get("actor_roll_no", "").strip()
    branch = data.get("branch", "").strip()
    section = data.get("section", "").strip()
    if not actor_roll_no or not branch or not section:
        return jsonify({"message": "actor_roll_no, branch, and section are required."}), 400
    if branch not in BRANCHES or section not in SECTIONS:
        return jsonify({"message": "Invalid branch or section."}), 400

    conn = get_db_connection()
    actor = get_user(conn, actor_roll_no)
    if not actor or actor["role"] != "teacher":
        conn.close()
        return jsonify({"message": "Only teachers can view student list."}), 403

    rows = conn.execute(
        """
        SELECT roll_no, name, branch, section
        FROM students
        WHERE role = 'student' AND branch = ? AND section = ?
        ORDER BY roll_no
        """,
        (branch, section),
    ).fetchall()
    conn.close()
    return jsonify(
        {
            "students": [
                {
                    "roll_no": row["roll_no"],
                    "name": row["name"],
                    "branch": row["branch"],
                    "section": row["section"],
                }
                for row in rows
            ]
        }
    )


@app.route("/add_student", methods=["POST"])
def add_student():
    """
    Teacher adds a new student (dynamic onboarding).
    Request JSON:
      {
        "actor_roll_no": "teacher1",
        "roll_no": "...",
        "name": "...",
        "dob": "YYYY-MM-DD",
        "branch": "CSE",
        "section": "A",
        "email": "student@example.com"
      }
    """
    data = request.get_json(silent=True) or {}
    actor_roll_no = data.get("actor_roll_no", "").strip()

    roll_no = str(data.get("roll_no", "")).strip()
    name = str(data.get("name", "")).strip()
    dob = str(data.get("dob", "")).strip()
    branch = str(data.get("branch", "")).strip()
    section = str(data.get("section", "")).strip()
    email = str(data.get("email", "")).strip()

    if not actor_roll_no:
        return jsonify({"message": "actor_roll_no is required."}), 400

    if not roll_no or not name or not dob or not branch or not section or not email:
        return jsonify({"message": "All fields are required."}), 400

    if branch not in BRANCHES or section not in SECTIONS:
        return jsonify({"message": "Invalid branch or section."}), 400

    conn = get_db_connection()
    actor = get_user(conn, actor_roll_no)
    if not actor or actor["role"] != "teacher":
        conn.close()
        return jsonify({"message": "Only teachers can add students."}), 403

    existing = conn.execute("SELECT roll_no FROM students WHERE roll_no = ?", (roll_no,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"message": "Student already exists"}), 409

    # Insert student.
    conn.execute(
        """
        INSERT INTO students (roll_no, dob, attended, total, role, name, branch, section, email)
        VALUES (?, ?, 0, 0, 'student', ?, ?, ?, ?)
        """,
        (roll_no, dob, name, branch, section, email),
    )

    # Auto-create subject-wise attendance records for the student.
    for subject in SUBJECTS:
        conn.execute(
            """
            INSERT OR IGNORE INTO attendance_records (roll_no, subject, attended, total, branch, section)
            VALUES (?, ?, 0, 0, ?, ?)
            """,
            (roll_no, subject, branch, section),
        )

    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Student added successfully."})


@app.route("/bulk_attendance_subject", methods=["POST"])
def bulk_attendance_subject():
    """
    Teacher marks attendance for one subject for an entire class.
    Request JSON:
      {
        "actor_roll_no": "teacher1",
        "branch": "CSE",
        "section": "A",
        "subject": "Math",
        "records": [
          { "roll_no": "24NN1A0501", "present": true },
          { "roll_no": "24NN1A0502", "present": false }
        ]
      }
    """
    data = request.get_json(silent=True) or {}
    actor_roll_no = data.get("actor_roll_no", "").strip()
    branch = data.get("branch", "").strip()
    section = data.get("section", "").strip()
    subject = data.get("subject", "").strip()
    records = data.get("records", [])

    if (
        not actor_roll_no
        or not branch
        or not section
        or not subject
        or branch not in BRANCHES
        or section not in SECTIONS
        or subject not in SUBJECTS
        or not isinstance(records, list)
        or not records
    ):
        return jsonify({"message": "actor_roll_no, branch, section, valid subject, and non-empty records are required."}), 400

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

        student_class = conn.execute(
            "SELECT branch, section FROM students WHERE roll_no = ?",
            (roll_no,),
        ).fetchone()
        if not student_class or student_class["branch"] != branch or student_class["section"] != section:
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
                , branch = ?, section = ?
            WHERE roll_no = ? AND subject = ?
            """,
            (attended, total, branch, section, roll_no, subject),
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
            "branch": branch,
            "section": section,
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

    # Send email warning only for students (and only once per cooldown).
    overall_pct = dashboard.get("overall", {}).get("percentage", 0)
    if actor["role"] == "student" and actor_roll_no == roll_no and overall_pct < EMAIL_WARNING_THRESHOLD:
        to_email = student["email"] if student else ""
        student_name = student["name"] if student else ""

        if not to_email:
            print("Email not configured. Skipping email send.")
        else:
            now_ts = time.time()
            last_ts = last_email_sent_ts_by_roll.get(roll_no, 0)
            if now_ts - last_ts >= EMAIL_COOLDOWN_SECONDS:
                send_result = send_email(to_email, student_name, float(overall_pct))
                if send_result.get("ok"):
                    last_email_sent_ts_by_roll[roll_no] = now_ts
                    print(f"Email sent to {to_email}")
                else:
                    # send_email already printed reason
                    pass
            else:
                print("Email skipped due to cooldown")
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
                "name": dashboard["welcome"]["name"],
                "branch": dashboard["welcome"]["class_str"].split("-")[0] if dashboard["welcome"]["class_str"] else "",
                "section": dashboard["welcome"]["class_str"].split("-")[1] if dashboard["welcome"]["class_str"] else "",
                "percentage": dashboard["overall"]["percentage"],
                "alert": dashboard["overall"]["alert"],
                "attended": dashboard["overall"]["attended"],
                "total": dashboard["overall"]["total"],
                "message": dashboard["overall"]["message"],
            }
        )

    conn.close()
    return jsonify({"students": all_rows})


if __name__ == "__main__":
    # Initialize DB before starting server.
    init_db()
    app.run(debug=True)
