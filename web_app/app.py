from flask import Flask, render_template, request, redirect, session, jsonify, send_file, flash, send_from_directory, abort
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import mysql.connector
import requests
import os
import json
import re
import uuid
from db_config import DB_CONFIG
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import RequestEntityTooLarge


app = Flask(__name__)
app.secret_key = "G7xQp9_2026_AttendanceSystem_SECRET_4mN82vZ_kL"
MODEL_REGISTRATION_URL = "http://host.docker.internal:6000/register-face"

# =========================
# PRIVATE UPLOADS CONFIG
# =========================
# Important:
# Files inside "static" can be opened directly by URL.
# Sensitive files such as excuse attachments and classroom snapshots are stored
# outside static, then served only through protected Flask routes.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PRIVATE_UPLOAD_ROOT = os.path.join(BASE_DIR, "private_uploads")

EXCUSE_UPLOAD_FOLDER = os.path.join(
    PRIVATE_UPLOAD_ROOT,
    "excuses"
)

SNAPSHOT_PRIVATE_DIR = os.path.join(
    PRIVATE_UPLOAD_ROOT,
    "live-result"
)

# Kept for existing upload code compatibility.
UPLOAD_FOLDER = EXCUSE_UPLOAD_FOLDER

# Store a relative private path in the database for new excuse attachments.
UPLOAD_DB_PATH_PREFIX = "excuses"

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_REASON_LENGTH = 1000
AMMAN_TZ = ZoneInfo("Asia/Amman")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

os.makedirs(EXCUSE_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SNAPSHOT_PRIVATE_DIR, exist_ok=True)

def get_file_extension(filename):
    if not filename or "." not in filename:
        return ""

    return filename.rsplit(".", 1)[1].lower()


def allowed_file(filename):
    return get_file_extension(filename) in ALLOWED_EXTENSIONS


def normalize_stored_upload_path(stored_path):
    """
    Converts old database paths such as:
      uploads/excuses/file.pdf
      static/uploads/excuses/file.pdf

    and new database paths such as:
      excuses/file.pdf

    into a safe relative path under private_uploads.
    """
    if not stored_path:
        return None

    clean_path = str(stored_path).replace("\\", "/").strip().lstrip("/")

    # Backward compatibility with old records saved under static/uploads.
    if clean_path.startswith("static/uploads/"):
        clean_path = clean_path[len("static/uploads/"):]

    if clean_path.startswith("uploads/"):
        clean_path = clean_path[len("uploads/"):]

    return clean_path


def build_private_file_path(private_root, relative_path):
    """
    Safely builds a file path under a private root folder.
    Prevents path traversal such as ../../secret.txt.
    """
    if not relative_path:
        return None

    clean_path = normalize_stored_upload_path(relative_path)

    if not clean_path:
        return None

    normalized_path = os.path.normpath(clean_path)

    if normalized_path.startswith("..") or os.path.isabs(normalized_path):
        return None

    full_path = os.path.abspath(os.path.join(private_root, normalized_path))
    private_root_abs = os.path.abspath(private_root)

    if not full_path.startswith(private_root_abs + os.sep):
        return None

    return full_path


def build_private_excuse_file_path(stored_path):
    """
    Maps an excuse_request.file_path value to private_uploads/excuses.
    Existing DB values may be uploads/excuses/filename.ext.
    New DB values are excuses/filename.ext.
    """
    clean_path = normalize_stored_upload_path(stored_path)

    if not clean_path:
        return None

    filename = os.path.basename(clean_path)

    if not filename:
        return None

    return os.path.join(EXCUSE_UPLOAD_FOLDER, filename)


def is_valid_upload_content(file, ext):
    """
    Validates the real uploaded file content using file signatures.
    More flexible for PDFs because some valid PDFs may not start exactly at byte 0.
    """
    file.seek(0)
    header = file.read(1024)
    file.seek(0)

    if ext == "pdf":
        return b"%PDF" in header[:1024]

    if ext == "png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")

    if ext in {"jpg", "jpeg"}:
        return header.startswith(b"\xff\xd8\xff")

    return False
def save_excuse_attachment(file, student_id):
    """
    Saves an excuse attachment after validating extension, content, and filename.
    Returns: (file_path_for_database, error_message)
    """
    raw_filename = file.filename or ""
    ext = get_file_extension(raw_filename)

    if not ext:
      return None, "Invalid file name."

    if ext not in ALLOWED_EXTENSIONS:
      return None, "Allowed file types are PDF, JPG, JPEG, and PNG only."
    if not is_valid_upload_content(file, ext):
        return None, "Invalid file content. Please upload a real PDF, JPG, JPEG, or PNG file."

    final_filename = f"{student_id}_{uuid.uuid4().hex}.{ext}"

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], final_filename)
    file.save(save_path)

    return f"{UPLOAD_DB_PATH_PREFIX}/{final_filename}", None

def contains_code_like_content(text):
    """
    Detects code-like content in the excuse reason.
    This helps prevent students from submitting HTML, JavaScript, SQL, or script code.
    """
    if not text:
        return False

    code_patterns = [
        r"<\s*script",
        r"<\s*/\s*script\s*>",
        r"<\s*[^>]+>",
        r"javascript\s*:",
        r"onerror\s*=",
        r"onclick\s*=",
        r"onload\s*=",

        r"\bSELECT\b",
        r"\bINSERT\b",
        r"\bUPDATE\b",
        r"\bDELETE\b",
        r"\bDROP\b",
        r"\bALTER\b",
        r"\bUNION\b",

        r"\bimport\s+\w+",
        r"\bdef\s+\w+\s*\(",
        r"\bclass\s+\w+",
        r"\bfunction\s+\w*\s*\(",
        r"console\.log\s*\(",
        r"print\s*\(",

    ]

    for pattern in code_patterns:
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            return True

    return False

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(error):
    flash("Uploaded file is too large. Maximum allowed size is 5 MB.", "error")
    return redirect(request.referrer or "/"), 413

# =========================
# DATABASE CONNECTION
# =========================

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def fetch_one(query, params=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(query, params or ())
    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return result


def fetch_all(query, params=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(query, params or ())
    results = cursor.fetchall()

    cursor.close()
    conn.close()

    return results


def execute_query(query, params=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(query, params or ())
    conn.commit()

    last_id = cursor.lastrowid

    cursor.close()
    conn.close()

    return last_id


# =========================
# HELPERS
# =========================

def is_admin():
    return session.get("role") == "admin"


def is_instructor():
    return session.get("role") == "instructor"


def is_student():
    return session.get("role") == "student"


def format_time_value(value):
    """
    Converts MySQL TIME / timedelta / string to HH:MM format.
    """
    if value is None:
        return ""

    if hasattr(value, "total_seconds"):
        total_seconds = int(value.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"

    text = str(value)

    if ":" in text:
        parts = text.split(":")
        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            return f"{hours:02d}:{minutes:02d}"
        except:
            return text[:5]

    return text
def get_current_semester_period():
    today = date.today()
    year = today.year

    # First Semester: Oct 15 -> Feb 28
    if today.month >= 10:
        return {
            "semester_name": "First Semester",
            "start_date": date(year, 10, 15),
            "end_date": date(year + 1, 2, 28)
        }

    if today.month in [1, 2]:
        return {
            "semester_name": "First Semester",
            "start_date": date(year - 1, 10, 15),
            "end_date": date(year, 2, 28)
        }

    # Second Semester: Mar 15 -> Jun 30
    if 3 <= today.month <= 6:
        return {
            "semester_name": "Second Semester",
            "start_date": date(year, 3, 15),
            "end_date": date(year, 6, 30)
        }


    # Summer Semester: Jul 21 -> Sep 15
    return {
        "semester_name": "Summer Semester",
        "start_date": date(year, 7, 21),
        "end_date": date(year, 9, 15)
    }
def parse_section_days(days_text):
    day_map = {
        "mon": 0,
        "monday": 0,
        "tue": 1,
        "tuesday": 1,
        "wed": 2,
        "wednesday": 2,
        "thu": 3,
        "thursday": 3,
        "fri": 4,
        "friday": 4,
        "sat": 5,
        "saturday": 5,
        "sun": 6,
        "sunday": 6
    }

    cleaned = str(days_text)
    cleaned = cleaned.replace("{", "")
    cleaned = cleaned.replace("}", "")
    cleaned = cleaned.replace("'", "")
    cleaned = cleaned.replace('"', "")
    cleaned = cleaned.replace(" ", "")

    parts = cleaned.split(",")

    result = []

    for p in parts:
        key = p.lower()

        if key in day_map:
            result.append(day_map[key])

    return result


def get_hours_between(start_time, end_time):
    start_text = format_time_value(start_time)
    end_text = format_time_value(end_time)

    start_dt = datetime.strptime(start_text, "%H:%M")
    end_dt = datetime.strptime(end_text, "%H:%M")

    difference = end_dt - start_dt

    return round(difference.total_seconds() / 3600, 2)


def calculate_expected_section_hours(day_of_week, start_time, end_time):
    semester = get_current_semester_period()

    start_date = semester["start_date"]
    end_date = semester["end_date"]

    section_days = parse_section_days(day_of_week)
    lecture_hours = get_hours_between(start_time, end_time)

    expected_lectures = 0
    current_date = start_date

    while current_date <= end_date:
        if current_date.weekday() in section_days:
            expected_lectures += 1

        current_date += timedelta(days=1)

    expected_hours = round(expected_lectures * lecture_hours, 2)

    return {
        "semester_name": semester["semester_name"],
        "semester_start_date": start_date,
        "semester_end_date": end_date,
        "expected_lectures": expected_lectures,
        "lecture_hours": lecture_hours,
        "expected_hours": expected_hours
    }

def get_course(course_id):
    course = fetch_one(
        """
        SELECT 
            `section`.section_id AS id,
            course.course_name AS name,
            CONCAT('Section ', `section`.section_id) AS section,
            `section`.day_of_week AS day,
            `section`.start_time AS start_time,
            `section`.end_time AS end_time,
            `section`.lecturer_id AS instructor_id
        FROM `section`
        JOIN course ON `section`.course_id = course.course_id
        WHERE `section`.section_id = %s
        """,
        (course_id,)
    )

    if course:
        course["start_time"] = format_time_value(course["start_time"])
        course["end_time"] = format_time_value(course["end_time"])

    return course


def get_instructor_courses():

    instructor_id = session.get("user_id")

    instructor_courses = fetch_all(
        """
        SELECT 
            `section`.section_id AS id,
            course.course_name AS name,
            CONCAT('Section ', `section`.section_id) AS section,
            `section`.day_of_week AS day,
            `section`.start_time AS start_time,
            `section`.end_time AS end_time,
            `section`.lecturer_id AS instructor_id
        FROM `section`
        JOIN course ON `section`.course_id = course.course_id
        WHERE `section`.lecturer_id = %s
        ORDER BY course.course_name, `section`.section_id
        """,
        (instructor_id,)
    )

    for c in instructor_courses:
        c["start_time"] = format_time_value(c["start_time"])
        c["end_time"] = format_time_value(c["end_time"])

    return instructor_courses


def get_all_courses_sections():

    all_courses = fetch_all(
        """
        SELECT 
            `section`.section_id AS id,
            course.course_name AS name,
            CONCAT('Section ', `section`.section_id) AS section,
            `section`.day_of_week AS day,
            `section`.start_time AS start_time,
            `section`.end_time AS end_time,
            `section`.lecturer_id AS instructor_id
        FROM `section`
        JOIN course ON `section`.course_id = course.course_id
        ORDER BY course.course_name, `section`.section_id
        """
    )

    for c in all_courses:
        c["start_time"] = format_time_value(c["start_time"])
        c["end_time"] = format_time_value(c["end_time"])

    return all_courses


def get_students_for_courses(instructor_courses):

    section_ids = [c["id"] for c in instructor_courses]

    if not section_ids:
        return []

    placeholders = ",".join(["%s"] * len(section_ids))

    return fetch_all(
        f"""
        SELECT DISTINCT
            student.student_id AS id,
            student.university_id AS university_id,
            student.full_name AS name,
            student.department AS dept
        FROM section_students
        JOIN student ON section_students.student_id = student.student_id
        WHERE section_students.section_id IN ({placeholders})
        AND student.is_active = 1
        ORDER BY student.full_name
        """,
        tuple(section_ids)
    )


def get_students_for_section(section_id):

    return fetch_all(
        """
        SELECT 
            student.student_id AS id,
            student.university_id AS university_id,
            student.full_name AS name,
            student.department AS dept
        FROM section_students
        JOIN student ON section_students.student_id = student.student_id
        WHERE section_students.section_id = %s
        AND student.is_active = 1
        ORDER BY student.full_name
        """,
        (section_id,)
    )

def is_course_active_now(course):

    now = datetime.now(AMMAN_TZ)

    current_day_short = now.strftime("%a")
    current_day_full = now.strftime("%A")

    days_text = str(course["day"])
    days_text = days_text.replace("{", "")
    days_text = days_text.replace("}", "")
    days_text = days_text.replace("'", "")
    days_text = days_text.replace('"', "")
    days_text = days_text.replace(" ", "")

    course_days = days_text.split(",")

    start_time_str = format_time_value(course["start_time"])
    end_time_str = format_time_value(course["end_time"])

    current_time_obj = now.time().replace(microsecond=0)

    start_time_obj = datetime.strptime(
        start_time_str,
        "%H:%M"
    ).time()

    end_time_obj = datetime.strptime(
        end_time_str,
        "%H:%M"
    ).time()

    return (
        (current_day_short in course_days or current_day_full in course_days)
        and start_time_obj <= current_time_obj <= end_time_obj
    )
def get_active_courses_now(instructor_courses):
    return [
        c for c in instructor_courses
        if is_course_active_now(c)
    ]


def format_session_row(row):
    if row is None:
        return None

    return {
        "session_id": row["session_id"],
        "course_id": row["section_id"],
        "status": "active" if row["is_active"] == 1 else "closed",
        "session_date": row["session_date"],
        "start_time": format_time_value(row["start_time"]),
        "end_time": format_time_value(row["end_time"])
    }


def get_session_by_id(session_id):
    row = fetch_one(
        """
        SELECT 
            session_id,
            section_id,
            session_date,
            start_time,
            end_time,
            is_active
        FROM `session`
        WHERE session_id = %s
        """,
        (session_id,)
    )

    return format_session_row(row)


def get_sessions_for_courses(instructor_courses):

    section_ids = [c["id"] for c in instructor_courses]

    if not section_ids:
        return []

    placeholders = ",".join(["%s"] * len(section_ids))

    rows = fetch_all(
        f"""
        SELECT 
            session_id,
            section_id,
            session_date,
            start_time,
            end_time,
            is_active
        FROM `session`
        WHERE section_id IN ({placeholders})
        ORDER BY session_date DESC, start_time DESC
        """,
        tuple(section_ids)
    )

    return [
        format_session_row(row)
        for row in rows
    ]


def get_attendance_for_sessions(instructor_sessions):

    session_ids = [s["session_id"] for s in instructor_sessions]

    if not session_ids:
        return []

    placeholders = ",".join(["%s"] * len(session_ids))

    return fetch_all(
        f"""
        SELECT 
            attendance_id,
            session_id,
            student_id,
            status,
            recognition_time
        FROM attendance
        WHERE session_id IN ({placeholders})
        """,
        tuple(session_ids)
    )


# =========================
# LOGIN
# =========================

@app.route("/")
def login():

    if session.get("role") == "admin":
        return redirect("/admin-dashboard")

    if session.get("role") == "instructor":
        return redirect("/instructor-dashboard")

    if session.get("role") == "student":
        return redirect("/student-dashboard")

    return render_template("login.html")
@app.route("/login", methods=["POST"])
def handle_login():

    username = request.form.get("username")
    password = request.form.get("password")

    user = fetch_one(
        """
        SELECT user_id, username, password_hash, full_name, role, student_id
        FROM users
        WHERE username = %s
        AND is_active = 1
        """,
        (username,)
    )

    stored_password = user["password_hash"] if user else None

    password_is_valid = False

    if user and stored_password:
        try:
            password_is_valid = check_password_hash(stored_password, password)
        except ValueError:
            password_is_valid = False

        if not password_is_valid and stored_password == password:
            password_is_valid = True

    if user and password_is_valid:
        session["role"] = user["role"]
        session["username"] = user["username"]
        session["user_id"] = user["user_id"]
        session["full_name"] = user["full_name"]

        if user["role"] == "admin":
            return redirect("/admin-dashboard")

        elif user["role"] == "instructor":
            return redirect("/instructor-dashboard")

        elif user["role"] == "student":
            session["student_id"] = user["student_id"]
            session["university_id"] = user["username"]
            return redirect("/student-dashboard")

    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/change-password", methods=["GET", "POST"])
def change_password():

    if "user_id" not in session:
        return redirect("/")

    error = None
    success = None

    if request.method == "POST":

        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not current_password or not new_password or not confirm_password:
            error = "Please fill in all fields."

        elif new_password != confirm_password:
            error = "New password and confirmation do not match."

        elif len(new_password) < 8:
            error = "New password must be at least 8 characters."

        else:
            user = fetch_one(
                """
                SELECT user_id, password_hash
                FROM users
                WHERE user_id = %s
                AND is_active = 1
                """,
                (session.get("user_id"),)
            )

            if not user:
                session.clear()
                return redirect("/")

            stored_password = user["password_hash"]

            password_is_valid = False

            try:
                password_is_valid = check_password_hash(stored_password, current_password)
            except ValueError:
                password_is_valid = False

            if not password_is_valid and stored_password == current_password:
                password_is_valid = True

            if not password_is_valid:
                error = "Current password is incorrect."

            else:
                new_hashed_password = generate_password_hash(new_password)

                execute_query(
                    """
                    UPDATE users
                    SET password_hash = %s
                    WHERE user_id = %s
                    """,
                    (
                        new_hashed_password,
                        session.get("user_id")
                    )
                )

                success = "Password changed successfully."

    return render_template(
        "change_password.html",
        error=error,
        success=success,
        user_role=session.get("role")
    )
# =========================
# DASHBOARDS
# =========================
@app.route("/admin-dashboard")
def admin_dashboard():

    if not is_admin():
        return redirect("/")

    today_date = datetime.now().date()

    today_sessions_result = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM `session`
        WHERE session_date = %s
        """,
        (today_date,)
    )

    active_sessions_result = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM `session`
        WHERE is_active = 1
        """
    )

    completed_today_result = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM `session`
        WHERE session_date = %s
        AND is_active = 0
        """,
        (today_date,)
    )

    attendance_today_result = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM attendance
        JOIN `session`
            ON attendance.session_id = `session`.session_id
        WHERE `session`.session_date = %s
        """,
        (today_date,)
    )

    today_sessions = today_sessions_result["total"] if today_sessions_result else 0
    active_sessions = active_sessions_result["total"] if active_sessions_result else 0
    completed_today = completed_today_result["total"] if completed_today_result else 0
    attendance_today = attendance_today_result["total"] if attendance_today_result else 0

    return render_template(
        "admin_dashboard.html",
        today_sessions=today_sessions,
        active_sessions=active_sessions,
        completed_today=completed_today,
        attendance_today=attendance_today
    )
@app.route("/instructor-dashboard")
def instructor_dashboard():

    if not is_instructor():
        return redirect("/")

    instructor_id = session.get("user_id")

    instructor_courses = get_instructor_courses()
    active_courses = get_active_courses_now(instructor_courses)

    instructor_sessions = get_sessions_for_courses(instructor_courses)
    instructor_attendance = get_attendance_for_sessions(instructor_sessions)

    current_lectures = []

    pending_excuses_result = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM excuse_request
        JOIN `section`
            ON excuse_request.section_id = `section`.section_id
        WHERE `section`.lecturer_id = %s
        AND excuse_request.status = 'pending'
        """,
        (instructor_id,)
    )

    pending_excuses = pending_excuses_result["total"] if pending_excuses_result else 0

    for course in active_courses:

        active_session_row = fetch_one(
            """
            SELECT 
                session_id,
                section_id,
                session_date,
                start_time,
                end_time,
                is_active
            FROM `session`
            WHERE section_id = %s
            AND is_active = 1
            ORDER BY session_id DESC
            LIMIT 1
            """,
            (course["id"],)
        )

        active_session = format_session_row(active_session_row)

        closed_session = fetch_one(
            """
            SELECT session_id
            FROM `session`
            WHERE section_id = %s
            AND session_date = CURDATE()
            AND is_active = 0
            LIMIT 1
            """,
            (course["id"],)
        )

        current_lectures.append({
            "course": course,
            "active_session": active_session,
            "closed_session": closed_session
        })

    today_day = datetime.now(AMMAN_TZ).strftime("%A")
    total_today_lectures = 0

    for course in instructor_courses:
        if course.get("day") == today_day:
            total_today_lectures += 1

    return render_template(
        "instructor_dashboard.html",
        courses=instructor_courses,
        active_courses=active_courses,
        current_lectures=current_lectures,
        total_courses=len(instructor_courses),
        total_sessions=len(instructor_sessions),
        total_attendance=len(instructor_attendance),
        pending_excuses=pending_excuses,
        total_today_lectures=total_today_lectures
    )
@app.route("/student-dashboard")
def student_dashboard():

    if not is_student():
        return redirect("/student-login")

    student_id = session.get("student_id")

    student = fetch_one(
        """
        SELECT
            student_id,
            university_id,
            full_name,
            department
        FROM student
        WHERE student_id = %s
        AND is_active = 1
        """,
        (student_id,)
    )

    if not student:
        session.clear()
        return redirect("/student-login")

    courses_absence = fetch_all(
        """
        SELECT
            `section`.section_id,
            course.course_name,
            CONCAT('Section ', `section`.section_id) AS section_name,

            COUNT(DISTINCT `session`.session_id) AS total_sessions,

            COUNT(DISTINCT attendance.attendance_id) AS present_count,

            COUNT(DISTINCT
                CASE
                    WHEN attendance.attendance_id IS NULL
                    AND excuse_request.excuse_id IS NOT NULL
                    THEN `session`.session_id
                END
            ) AS excused_count,

            (
                COUNT(DISTINCT `session`.session_id)
                -
                COUNT(DISTINCT attendance.attendance_id)
                -
                COUNT(DISTINCT
                    CASE
                        WHEN attendance.attendance_id IS NULL
                        AND excuse_request.excuse_id IS NOT NULL
                        THEN `session`.session_id
                    END
                )
            ) AS absent_count

        FROM section_students

        JOIN `section`
            ON section_students.section_id = `section`.section_id

        JOIN course
            ON `section`.course_id = course.course_id

        LEFT JOIN `session`
            ON `section`.section_id = `session`.section_id
            AND `session`.is_active = 0

        LEFT JOIN attendance
            ON attendance.session_id = `session`.session_id
            AND attendance.student_id = section_students.student_id
            AND attendance.status = 'Present'

        LEFT JOIN excuse_request
            ON excuse_request.student_id = section_students.student_id
            AND excuse_request.section_id = `section`.section_id
            AND excuse_request.status = 'approved'
            AND (
                excuse_request.session_id = `session`.session_id
                OR (
                    excuse_request.session_id IS NULL
                    AND excuse_request.excuse_date = `session`.session_date
                )
            )

        WHERE section_students.student_id = %s

        GROUP BY
            `section`.section_id,
            course.course_name,
            section_name

        ORDER BY course.course_name, `section`.section_id
        """,
        (student_id,)
    )


    
    my_excuses = fetch_all(
      """
      SELECT
          excuse_request.excuse_id,
          excuse_request.excuse_date,
          excuse_request.reason,
          excuse_request.status,
          excuse_request.instructor_note,
          excuse_request.submitted_at,
          excuse_request.reviewed_at,

          course.course_name,
          `section`.section_id

      FROM excuse_request

      JOIN `section`
          ON excuse_request.section_id = `section`.section_id

      JOIN course
          ON `section`.course_id = course.course_id

      WHERE excuse_request.student_id = %s

      ORDER BY excuse_request.submitted_at DESC
      LIMIT 5
      """,
      (student_id,)
    )

    return render_template(
        "student_dashboard.html",
        student=student,
        courses_absence=courses_absence,
        my_excuses=my_excuses
    )
# =========================
# SESSIONS
# =========================
@app.route("/start-session/<int:course_id>")
def start_session(course_id):

    if not is_instructor():
        return redirect("/")

    instructor_courses = get_instructor_courses()

    course = next(
        (c for c in instructor_courses if c["id"] == course_id),
        None
    )

    if course is None:
        flash("You are not allowed to start a session for this section.", "error")
        return redirect("/instructor-dashboard")

    if not is_course_active_now(course):
        flash("This lecture is not scheduled right now.", "error")
        return redirect("/instructor-dashboard")

    existing_session = fetch_one(
        """
        SELECT 
            session_id,
            section_id,
            session_date,
            start_time,
            end_time,
            is_active
        FROM `session`
        WHERE section_id = %s
        AND session_date = CURDATE()
        AND is_active = 1
        ORDER BY session_id DESC
        LIMIT 1
        """,
        (course_id,)
    )

    if existing_session:
        flash("This section already has an active session today.", "info")
        return redirect(f"/attendance/{existing_session['session_id']}")

    if course_id != 1:
        closed_session_today = fetch_one(
            """
            SELECT session_id
            FROM `session`
            WHERE section_id = %s
            AND session_date = CURDATE()
            AND is_active = 0
            LIMIT 1
            """,
            (course_id,)
        )

        if closed_session_today:
            flash("This section already has a completed session today. You cannot start it again today.", "error")
            return redirect("/instructor-dashboard")

    new_session_id = execute_query(
        """
        INSERT INTO `session`
        (section_id, session_date, start_time, end_time, is_active, started_by)
        VALUES (%s, CURDATE(), %s, %s, 1, %s)
        """,
        (
            course_id,
            course["start_time"],
            course["end_time"],
            session.get("user_id")
        )
    )

    flash("Session started successfully.", "success")
    return redirect(f"/attendance/{new_session_id}")


@app.route("/end-session/<int:session_id>")
def end_session(session_id):

    if not is_instructor():
        return redirect("/")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        flash("Session not found.", "error")
        return redirect("/instructor-dashboard")

    instructor_section_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if current_session["course_id"] not in instructor_section_ids:
        flash("You are not allowed to end this session.", "error")
        return redirect("/instructor-dashboard")

    if current_session["status"] == "closed":
        flash("This session is already completed.", "info")
        return redirect(f"/attendance/{session_id}")

    execute_query(
        """
        UPDATE `session`
        SET is_active = 0
        WHERE session_id = %s
        """,
        (session_id,)
    )

    flash("Session ended successfully.", "success")
    return redirect(f"/attendance/{session_id}")
# =========================
# ATTENDANCE - LIVE SESSION PAGE
# =========================
@app.route("/attendance/<int:session_id>")
def attendance_page(session_id):

    if not is_instructor():
        return redirect("/")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        flash("Session not found.", "error")
        return redirect("/instructor-dashboard")

    instructor_section_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if current_session["course_id"] not in instructor_section_ids:
        flash("You are not allowed to view this session.", "error")
        return redirect("/instructor-dashboard")

    course = get_course(current_session["course_id"])

    session_students = get_students_for_section(current_session["course_id"])

    session_attendance = fetch_all(
        """
        SELECT 
            attendance_id,
            session_id,
            student_id,
            status,
            recognition_time
        FROM attendance
        WHERE session_id = %s
        AND status = 'Present'
        """,
        (session_id,)
    )

    present_student_ids = set(
        str(a["student_id"]) for a in session_attendance
    )

    approved_excuses = fetch_all(
        """
        SELECT
            excuse_request.student_id
        FROM excuse_request
        WHERE excuse_request.section_id = %s
        AND excuse_request.status = 'approved'
        AND (
            excuse_request.session_id = %s
            OR (
                excuse_request.session_id IS NULL
                AND excuse_request.excuse_date = %s
            )
        )
        """,
        (
            current_session["course_id"],
            session_id,
            current_session["session_date"]
        )
    )

    excused_student_ids = set(
        str(e["student_id"]) for e in approved_excuses
    )

    present_students = [
        s for s in session_students
        if str(s["id"]) in present_student_ids
    ]

    excused_students = [
        s for s in session_students
        if str(s["id"]) not in present_student_ids
        and str(s["id"]) in excused_student_ids
    ]

    absent_students = [
        s for s in session_students
        if str(s["id"]) not in present_student_ids
        and str(s["id"]) not in excused_student_ids
    ]

    total_students = len(session_students)
    total_present = len(present_students)
    total_excused = len(excused_students)
    total_absent = len(absent_students)

    if total_students > 0:
        attendance_percentage = int((total_present / total_students) * 100)
    else:
        attendance_percentage = 0

    return render_template(
        "attendance.html",
        session=current_session,
        course=course,
        present_students=present_students,
        absent_students=absent_students,
        excused_students=excused_students,
        total_students=total_students,
        total_present=total_present,
        total_excused=total_excused,
        total_absent=total_absent,
        attendance_percentage=attendance_percentage
    )

@app.route("/api/session-attendance/<int:session_id>")
def api_session_attendance(session_id):

    if not is_instructor():
        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    current_session = get_session_by_id(session_id)

    if current_session is None:
        return jsonify({
            "success": False,
            "message": "Session not found"
        }), 404

    instructor_section_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if current_session["course_id"] not in instructor_section_ids:
        return jsonify({
            "success": False,
            "message": "You do not have access to this session"
        }), 403

    session_students = get_students_for_section(current_session["course_id"])

    session_attendance = fetch_all(
        """
        SELECT 
            attendance_id,
            session_id,
            student_id,
            status,
            recognition_time
        FROM attendance
        WHERE session_id = %s
        AND status = 'Present'
        """,
        (session_id,)
    )

    attendance_map = {
        str(a["student_id"]): a
        for a in session_attendance
    }

    approved_excuses = fetch_all(
        """
        SELECT
            excuse_request.student_id
        FROM excuse_request
        WHERE excuse_request.section_id = %s
        AND excuse_request.status = 'approved'
        AND (
            excuse_request.session_id = %s
            OR (
                excuse_request.session_id IS NULL
                AND excuse_request.excuse_date = %s
            )
        )
        """,
        (
            current_session["course_id"],
            session_id,
            current_session["session_date"]
        )
    )

    excused_student_ids = set(
        str(e["student_id"]) for e in approved_excuses
    )

    present_students = []
    excused_students = []
    absent_students = []

    for s in session_students:

        student_id = str(s["id"])

        student_data = {
            "id": s["id"],
            "university_id": s["university_id"],
            "name": s["name"],
            "dept": s["dept"]
        }

        if student_id in attendance_map:

            recognition_time = attendance_map[student_id]["recognition_time"]

            student_data["recognition_time"] = (
                str(recognition_time) if recognition_time else ""
            )

            present_students.append(student_data)

        elif student_id in excused_student_ids:

            student_data["recognition_time"] = ""
            excused_students.append(student_data)

        else:
            absent_students.append(student_data)

    total_students = len(session_students)
    total_present = len(present_students)
    total_excused = len(excused_students)
    total_absent = len(absent_students)

    if total_students > 0:
        attendance_percentage = int((total_present / total_students) * 100)
    else:
        attendance_percentage = 0

    return jsonify({
        "success": True,
        "session_id": session_id,
        "status": current_session["status"],
        "total_students": total_students,
        "total_present": total_present,
        "total_excused": total_excused,
        "total_absent": total_absent,
        "attendance_percentage": attendance_percentage,
        "present_students": present_students,
        "excused_students": excused_students,
        "absent_students": absent_students
    }), 200
@app.route("/mark-attendance", methods=["POST"])
def mark_attendance():

    if not is_instructor():
        return redirect("/")

    student_id = request.form.get("student_id")
    session_id = request.form.get("session_id")

    if not student_id or not session_id:
        flash("Missing student or session information.", "error")
        return redirect("/instructor-dashboard")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        flash("Session not found.", "error")
        return redirect("/instructor-dashboard")

    instructor_section_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if current_session["course_id"] not in instructor_section_ids:
        flash("You are not allowed to mark attendance for this session.", "error")
        return redirect("/instructor-dashboard")

    if current_session["status"] != "active":
        flash("Attendance cannot be marked because this session is closed.", "error")
        return redirect(f"/attendance/{session_id}")

    allowed_student = fetch_one(
        """
        SELECT student_id
        FROM section_students
        WHERE section_id = %s
        AND student_id = %s
        """,
        (current_session["course_id"], student_id)
    )

    if allowed_student is None:
        flash("This student is not registered in this section.", "error")
        return redirect(f"/attendance/{session_id}")

    already_marked = fetch_one(
        """
        SELECT attendance_id
        FROM attendance
        WHERE session_id = %s
        AND student_id = %s
        """,
        (session_id, student_id)
    )

    if already_marked is None:
        execute_query(
            """
            INSERT INTO attendance
            (session_id, student_id, status, recognition_time)
            VALUES (%s, %s, %s, NOW())
            """,
            (session_id, student_id, "Present")
        )

        flash("Attendance marked successfully.", "success")

    else:
        flash("This student is already marked present.", "info")

    return redirect(f"/attendance/{session_id}")
@app.route("/attendance/<int:session_id>/manual-present/<int:student_id>", methods=["POST"])
def manual_mark_present(session_id, student_id):

    if not is_instructor():
        return redirect("/")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        flash("Session not found.", "error")
        return redirect("/instructor-dashboard")

    instructor_section_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if current_session["course_id"] not in instructor_section_ids:
        flash("You are not allowed to edit this session.", "error")
        return redirect("/instructor-dashboard")

    if current_session["status"] != "active":
        flash("You can only edit attendance while the session is active.", "error")
        return redirect(f"/attendance/{session_id}")

    allowed_student = fetch_one(
        """
        SELECT student_id
        FROM section_students
        WHERE section_id = %s
        AND student_id = %s
        """,
        (current_session["course_id"], student_id)
    )

    if allowed_student is None:
        flash("This student is not registered in this section.", "error")
        return redirect(f"/attendance/{session_id}")

    already_marked = fetch_one(
        """
        SELECT attendance_id
        FROM attendance
        WHERE session_id = %s
        AND student_id = %s
        """,
        (session_id, student_id)
    )

    if already_marked:
        flash("This student is already marked present.", "info")
        return redirect(f"/attendance/{session_id}")

    execute_query(
        """
        INSERT INTO attendance
        (session_id, student_id, status, recognition_time)
        VALUES (%s, %s, 'Present', NOW())
        """,
        (session_id, student_id)
    )

    flash("Student marked as present successfully.", "success")
    return redirect(f"/attendance/{session_id}")


@app.route("/attendance/<int:session_id>/manual-absent/<int:student_id>", methods=["POST"])
def manual_mark_absent(session_id, student_id):

    if not is_instructor():
        return redirect("/")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        flash("Session not found.", "error")
        return redirect("/instructor-dashboard")

    instructor_section_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if current_session["course_id"] not in instructor_section_ids:
        flash("You are not allowed to edit this session.", "error")
        return redirect("/instructor-dashboard")

    if current_session["status"] != "active":
        flash("You can only edit attendance while the session is active.", "error")
        return redirect(f"/attendance/{session_id}")

    execute_query(
        """
        DELETE FROM attendance
        WHERE session_id = %s
        AND student_id = %s
        """,
        (session_id, student_id)
    )

    flash("Student marked as absent successfully.", "success")
    return redirect(f"/attendance/{session_id}")
# =========================
# REPORTS
# =========================
def build_session_report_data(session_id):

    current_session = get_session_by_id(session_id)

    if current_session is None:
        return None

    course = get_course(current_session["course_id"])

    session_students = get_students_for_section(current_session["course_id"])

    session_attendance = fetch_all(
        """
        SELECT 
            attendance_id,
            session_id,
            student_id,
            status,
            recognition_time
        FROM attendance
        WHERE session_id = %s
        AND status = 'Present'
        """,
        (session_id,)
    )

    present_student_ids = set(
        str(a["student_id"]) for a in session_attendance
    )

    approved_excuses = fetch_all(
        """
        SELECT
            student_id
        FROM excuse_request
        WHERE section_id = %s
        AND status = 'approved'
        AND (
            session_id = %s
            OR (
                session_id IS NULL
                AND excuse_date = %s
            )
        )
        """,
        (
            current_session["course_id"],
            session_id,
            current_session["session_date"]
        )
    )

    excused_student_ids = set(
        str(e["student_id"]) for e in approved_excuses
    )

    report_students = []

    for s in session_students:

        student_id = str(s["id"])

        if student_id in present_student_ids:
            status = "Present"
        elif student_id in excused_student_ids:
            status = "Excused"
        else:
            status = "Absent"

        report_students.append({
            "id": s["id"],
            "name": s["name"],
            "dept": s["dept"],
            "status": status
        })

    total_students = len(session_students)
    total_present = len(present_student_ids)
    total_excused = len(excused_student_ids - present_student_ids)
    total_absent = total_students - total_present - total_excused

    if total_students > 0:
        attendance_percentage = int((total_present / total_students) * 100)
    else:
        attendance_percentage = 0

    return {
        "current_session": current_session,
        "course": course,
        "students": report_students,
        "total_students": total_students,
        "total_present": total_present,
        "total_excused": total_excused,
        "total_absent": total_absent,
        "attendance_percentage": attendance_percentage
    }


def build_section_report_data(section_id):

    course = get_course(section_id)

    if course is None:
        return None

    students = get_students_for_section(section_id)

    closed_sessions = fetch_all(
        """
        SELECT
            session_id,
            section_id,
            session_date,
            start_time,
            end_time,
            is_active
        FROM `session`
        WHERE section_id = %s
        AND is_active = 0
        ORDER BY session_date, start_time
        """,
        (section_id,)
    )

    if not closed_sessions:
        return {
            "course": course,
            "students_summary": [],
            "sessions_summary": [],
            "total_students": len(students),
            "total_sessions": 0,
            "total_present_records": 0,
            "total_excused_records": 0,
            "total_absent_records": 0,
            "overall_attendance_rate": 0,
            "best_session": None,
            "worst_session": None,
            "most_absent_students": []
        }

    session_ids = [
        s["session_id"] for s in closed_sessions
    ]

    placeholders = ",".join(["%s"] * len(session_ids))

    attendance_rows = fetch_all(
        f"""
        SELECT
            session_id,
            student_id
        FROM attendance
        WHERE session_id IN ({placeholders})
        AND status = 'Present'
        """,
        tuple(session_ids)
    )

    attendance_map = {}

    for row in attendance_rows:
        session_id = row["session_id"]
        student_id = row["student_id"]

        if session_id not in attendance_map:
            attendance_map[session_id] = set()

        attendance_map[session_id].add(student_id)

    approved_excuses = fetch_all(
        f"""
        SELECT
            student_id,
            session_id,
            excuse_date
        FROM excuse_request
        WHERE section_id = %s
        AND status = 'approved'
        AND (
            session_id IN ({placeholders})
            OR excuse_date IN (
                SELECT session_date
                FROM `session`
                WHERE session_id IN ({placeholders})
            )
        )
        """,
        tuple([section_id] + session_ids + session_ids)
    )

    excuse_map = {}

    for excuse in approved_excuses:

        for s in closed_sessions:

            same_session = (
                excuse["session_id"] is not None
                and excuse["session_id"] == s["session_id"]
            )

            same_date = (
                excuse["session_id"] is None
                and excuse["excuse_date"] == s["session_date"]
            )

            if same_session or same_date:

                session_id = s["session_id"]

                if session_id not in excuse_map:
                    excuse_map[session_id] = set()

                excuse_map[session_id].add(excuse["student_id"])

    total_students = len(students)
    total_sessions = len(closed_sessions)

    sessions_summary = []

    total_present_records = 0
    total_excused_records = 0
    total_absent_records = 0

    for s in closed_sessions:

        session_id = s["session_id"]

        present_ids = attendance_map.get(session_id, set())
        excused_ids = excuse_map.get(session_id, set())

        excused_ids = excused_ids - present_ids

        present_count = len(present_ids)
        excused_count = len(excused_ids)
        absent_count = total_students - present_count - excused_count

        total_present_records += present_count
        total_excused_records += excused_count
        total_absent_records += absent_count

        if total_students > 0:
            attendance_rate = int((present_count / total_students) * 100)
        else:
            attendance_rate = 0

        sessions_summary.append({
            "session_id": session_id,
            "session_date": s["session_date"],
            "start_time": format_time_value(s["start_time"]),
            "end_time": format_time_value(s["end_time"]),
            "present_count": present_count,
            "excused_count": excused_count,
            "absent_count": absent_count,
            "attendance_rate": attendance_rate
        })

    total_possible_records = total_students * total_sessions

    if total_possible_records > 0:
        overall_attendance_rate = int((total_present_records / total_possible_records) * 100)
    else:
        overall_attendance_rate = 0

    if sessions_summary:
        best_session = max(sessions_summary, key=lambda x: x["attendance_rate"])
        worst_session = min(sessions_summary, key=lambda x: x["attendance_rate"])
    else:
        best_session = None
        worst_session = None

    students_summary = []

    for student in students:

        student_id = student["id"]

        present_count = 0
        excused_count = 0

        for s in closed_sessions:

            session_id = s["session_id"]

            present_ids = attendance_map.get(session_id, set())
            excused_ids = excuse_map.get(session_id, set()) - present_ids

            if student_id in present_ids:
                present_count += 1
            elif student_id in excused_ids:
                excused_count += 1

        absent_count = total_sessions - present_count - excused_count

        if total_sessions > 0:
            attendance_rate = int((present_count / total_sessions) * 100)
        else:
            attendance_rate = 0

        students_summary.append({
            "student_id": student_id,
            "university_id": student["university_id"],
            "name": student["name"],
            "dept": student["dept"],
            "present_count": present_count,
            "excused_count": excused_count,
            "absent_count": absent_count,
            "attendance_rate": attendance_rate
        })

    most_absent_students = sorted(
        students_summary,
        key=lambda x: x["absent_count"],
        reverse=True
    )[:5]

    return {
        "course": course,
        "students_summary": students_summary,
        "sessions_summary": sessions_summary,
        "total_students": total_students,
        "total_sessions": total_sessions,
        "total_present_records": total_present_records,
        "total_excused_records": total_excused_records,
        "total_absent_records": total_absent_records,
        "overall_attendance_rate": overall_attendance_rate,
        "best_session": best_session,
        "worst_session": worst_session,
        "most_absent_students": most_absent_students
    }


def build_course_charts_data(course_id):

    selected_course = fetch_one(
        """
        SELECT course_id, course_name
        FROM course
        WHERE course_id = %s
        """,
        (course_id,)
    )

    if not selected_course:
        return None

    instructor_filter_sql = ""
    params = [course_id]

    if is_instructor():

        instructor_id = session.get("user_id")

        allowed_course = fetch_one(
            """
            SELECT course.course_id
            FROM course
            JOIN `section`
                ON course.course_id = `section`.course_id
            WHERE course.course_id = %s
            AND `section`.lecturer_id = %s
            LIMIT 1
            """,
            (course_id, instructor_id)
        )

        if not allowed_course:
            return None

        instructor_filter_sql = "AND lecturer_id = %s"
        params.append(instructor_id)

    sections = fetch_all(
        f"""
        SELECT
            section_id
        FROM `section`
        WHERE course_id = %s
        {instructor_filter_sql}
        ORDER BY section_id
        """,
        tuple(params)
    )

    sections_summary = []
    students_summary_map = {}

    total_present = 0
    total_excused = 0
    total_absent = 0

    section_labels = []
    section_rates = []

    for section in sections:

        section_id = section["section_id"]

        section_report = build_section_report_data(section_id)

        if section_report is None:
            continue

        section_students = section_report["total_students"]
        section_sessions = section_report["total_sessions"]
        section_present = section_report["total_present_records"]
        section_excused = section_report["total_excused_records"]
        section_absent = section_report["total_absent_records"]
        section_rate = section_report["overall_attendance_rate"]

        total_present += section_present
        total_excused += section_excused
        total_absent += section_absent

        section_labels.append(f"Section {section_id}")
        section_rates.append(section_rate)

        sections_summary.append({
            "section_id": section_id,
            "section_name": f"Section {section_id}",
            "total_students": section_students,
            "total_sessions": section_sessions,
            "present_records": section_present,
            "excused_records": section_excused,
            "absent_records": section_absent,
            "attendance_rate": section_rate
        })

        for student in section_report["students_summary"]:

            student_id = student["student_id"]

            if student_id not in students_summary_map:
                students_summary_map[student_id] = {
                    "student_id": student_id,
                    "university_id": student["university_id"],
                    "full_name": student["name"],
                    "total_sessions": 0,
                    "present_count": 0,
                    "excused_count": 0,
                    "absent_count": 0,
                    "attendance_rate": 0
                }

            students_summary_map[student_id]["total_sessions"] += section_sessions
            students_summary_map[student_id]["present_count"] += student["present_count"]
            students_summary_map[student_id]["excused_count"] += student["excused_count"]
            students_summary_map[student_id]["absent_count"] += student["absent_count"]

    students_summary = list(students_summary_map.values())

    for student in students_summary:

        if student["total_sessions"] > 0:
            student["attendance_rate"] = int(
                (student["present_count"] / student["total_sessions"]) * 100
            )
        else:
            student["attendance_rate"] = 0

    most_absent_students = sorted(
        students_summary,
        key=lambda x: x["absent_count"],
        reverse=True
    )[:5]

    chart_data = {
        "present_absent": {
            "labels": ["Present", "Absent"],
            "values": [total_present, total_absent]
        },
        "section_rates": {
            "labels": section_labels,
            "values": section_rates
        },
        "most_absent": {
            "labels": [s["full_name"] for s in most_absent_students],
            "values": [s["absent_count"] for s in most_absent_students]
        }
    }

    total_records = total_present + total_excused + total_absent

    if total_records > 0:
        overall_attendance_rate = int((total_present / total_records) * 100)
    else:
        overall_attendance_rate = 0

    course_report_summary = {
        "total_students": len(students_summary),
        "total_sessions": sum(sec["total_sessions"] for sec in sections_summary),
        "total_present": total_present,
        "total_excused": total_excused,
        "total_absent": total_absent,
        "attendance_rate": overall_attendance_rate
    }

    show_section_breakdown = len(sections_summary) > 1

    return {
        "selected_course": selected_course,
        "chart_data": chart_data,
        "sections_summary": sections_summary,
        "students_summary": students_summary,
        "most_absent_students": most_absent_students,
        "course_report_summary": course_report_summary,
        "show_section_breakdown": show_section_breakdown
    }


def build_courses_summary_data():

    if is_admin():

        courses = fetch_all(
            """
            SELECT
                course_id,
                course_name
            FROM course
            ORDER BY course_name
            """
        )

    else:

        instructor_id = session.get("user_id")

        courses = fetch_all(
            """
            SELECT DISTINCT
                course.course_id,
                course.course_name
            FROM course
            JOIN `section`
                ON course.course_id = `section`.course_id
            WHERE `section`.lecturer_id = %s
            ORDER BY course.course_name
            """,
            (instructor_id,)
        )

    courses_summary = []

    for course in courses:

        report_data = build_course_charts_data(course["course_id"])

        if not report_data:
            continue

        summary = report_data["course_report_summary"]

        courses_summary.append({
            "course_id": course["course_id"],
            "course_name": course["course_name"],
            "total_sections": len(report_data["sections_summary"]),
            "total_students": summary["total_students"],
            "total_sessions": summary["total_sessions"],
            "total_present_records": summary["total_present"],
            "total_excused_records": summary["total_excused"],
            "total_absent_records": summary["total_absent"],
            "attendance_rate": summary["attendance_rate"]
        })

    return courses_summary


@app.route("/section-report/<int:section_id>")
def section_report(section_id):

    if session.get("role") not in ["admin", "instructor"]:
        return redirect("/")

    if section_id == 1:
        flash("This section is for testing only and is not included in official reports.", "info")
        return redirect("/reports")

    if is_instructor():

        instructor_section_ids = [
            c["id"] for c in get_instructor_courses()
        ]

        if section_id not in instructor_section_ids:
            flash("You are not allowed to view this section report.", "error")
            return redirect("/reports")

    report_data = build_section_report_data(section_id)

    if report_data is None:
        flash("Section report not found.", "error")
        return redirect("/reports")

    return render_template(
        "section_report.html",
        course=report_data["course"],
        students_summary=report_data["students_summary"],
        sessions_summary=report_data["sessions_summary"],
        total_students=report_data["total_students"],
        total_sessions=report_data["total_sessions"],
        total_present_records=report_data["total_present_records"],
        total_excused_records=report_data["total_excused_records"],
        total_absent_records=report_data["total_absent_records"],
        overall_attendance_rate=report_data["overall_attendance_rate"],
        best_session=report_data["best_session"],
        worst_session=report_data["worst_session"],
        most_absent_students=report_data["most_absent_students"],
        user_role=session.get("role")
    )


@app.route("/reports")
def reports():

    if session.get("role") not in ["admin", "instructor"]:
        return redirect("/")

    selected_course_id = request.args.get("course_id")

    courses_summary = build_courses_summary_data()

    selected_course = None
    chart_data = None
    sections_summary = []
    students_summary = []
    most_absent_students = []
    course_report_summary = None
    show_section_breakdown = False

    if selected_course_id:

        report_data = build_course_charts_data(selected_course_id)

        if report_data:
            selected_course = report_data.get("selected_course")
            chart_data = report_data.get("chart_data")
            sections_summary = report_data.get("sections_summary", [])
            students_summary = report_data.get("students_summary", [])
            most_absent_students = report_data.get("most_absent_students", [])
            course_report_summary = report_data.get("course_report_summary")
            show_section_breakdown = report_data.get("show_section_breakdown", False)

    return render_template(
        "reports.html",
        courses_summary=courses_summary,
        selected_course=selected_course,
        chart_data=chart_data,
        sections_summary=sections_summary,
        students_summary=students_summary,
        most_absent_students=most_absent_students,
        course_report_summary=course_report_summary,
        show_section_breakdown=show_section_breakdown,
        selected_course_id=selected_course_id,
        user_role=session.get("role")
    )
@app.route("/submit-excuse", methods=["GET", "POST"])
def submit_excuse():

    if not is_student():
        return redirect("/student-login")

    student_id = session.get("student_id")

    student = fetch_one(
        """
        SELECT student_id, university_id, full_name
        FROM student
        WHERE student_id = %s
        AND is_active = 1
        """,
        (student_id,)
    )

    if not student:
        session.clear()
        return redirect("/student-login")

    if request.method == "POST":

        section_id = request.form.get("section_id")
        excuse_date = request.form.get("excuse_date")
        reason = request.form.get("reason", "").strip()
        file = request.files.get("excuse_file")

        if not section_id or not excuse_date or not reason:
            flash("Please fill in all required fields.", "error")
            return redirect("/submit-excuse")

        if len(reason) > MAX_REASON_LENGTH:
            flash("Reason is too long. Please keep it under 1000 characters.", "error")
            return redirect("/submit-excuse")

        if contains_code_like_content(reason):
            flash("The excuse reason cannot contain code, HTML, scripts, or SQL commands.", "error")
            return redirect("/submit-excuse")
        try:
            section_id = int(section_id)
        except ValueError:
            flash("Invalid section selected.", "error")
            return redirect("/submit-excuse")

        try:
            parsed_excuse_date = datetime.strptime(excuse_date, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid absence date.", "error")
            return redirect("/submit-excuse")

        if parsed_excuse_date > datetime.now().date():
            flash("You cannot submit an excuse for a future date.", "error")
            return redirect("/submit-excuse")

        enrollment = fetch_one(
            """
            SELECT enrollment_id
            FROM section_students
            WHERE student_id = %s
            AND section_id = %s
            """,
            (student["student_id"], section_id)
        )

        if not enrollment:
            flash("This student is not registered in the selected section.", "error")
            return redirect("/submit-excuse")

        session_row = fetch_one(
            """
            SELECT session_id, is_active
            FROM `session`
            WHERE section_id = %s
            AND session_date = %s
            LIMIT 1
            """,
            (section_id, parsed_excuse_date)
        )

        if not session_row:
            flash("No attendance session was found for this section on the selected date.", "error")
            return redirect("/submit-excuse")

        if session_row["is_active"] == 1:
            flash("You cannot submit an excuse while the session is still active.", "error")
            return redirect("/submit-excuse")

        session_id = session_row["session_id"]

        already_present = fetch_one(
            """
            SELECT attendance_id
            FROM attendance
            WHERE session_id = %s
            AND student_id = %s
            AND status = 'Present'
            LIMIT 1
            """,
            (session_id, student["student_id"])
        )

        if already_present:
            flash("You were marked present in this session, so an excuse is not needed.", "info")
            return redirect("/submit-excuse")

        existing_excuse = fetch_one(
            """
            SELECT excuse_id, status
            FROM excuse_request
            WHERE student_id = %s
            AND section_id = %s
            AND excuse_date = %s
            AND status IN ('pending', 'approved')
            LIMIT 1
            """,
            (student["student_id"], section_id, parsed_excuse_date)
        )

        if existing_excuse:
            flash("You already submitted an excuse for this section and date.", "error")
            return redirect("/submit-excuse")

        file_path = None

        if file and file.filename:
            file_path, upload_error = save_excuse_attachment(
                file,
                student["student_id"]
            )

            if upload_error:
                flash(upload_error, "error")
                return redirect("/submit-excuse")

        execute_query(
            """
            INSERT INTO excuse_request
            (student_id, section_id, session_id, excuse_date, reason, file_path, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            """,
            (
                student["student_id"],
                section_id,
                session_id,
                parsed_excuse_date,
                reason,
                file_path
            )
        )

        flash("Your excuse request has been submitted successfully.", "success")
        return redirect("/submit-excuse")

    sections = fetch_all(
        """
        SELECT 
            `section`.section_id,
            course.course_name,
            CONCAT('Section ', `section`.section_id) AS section_name
        FROM `section`
        JOIN course
            ON `section`.course_id = course.course_id
        JOIN section_students
            ON `section`.section_id = section_students.section_id
        WHERE section_students.student_id = %s
        ORDER BY course.course_name, `section`.section_id
        """,
        (student["student_id"],)
    )

    return render_template(
        "submit_excuse.html",
        sections=sections,
        student=student
    )
@app.route("/session-report/<int:session_id>")
def session_report(session_id):

    if session.get("role") not in ["admin", "instructor"]:
        return redirect("/")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        flash("Session not found.", "error")
        return redirect("/reports")

    if is_instructor():
        instructor_section_ids = [
            c["id"] for c in get_instructor_courses()
        ]

        if current_session["course_id"] not in instructor_section_ids:
            flash("You are not allowed to view this session report.", "error")
            return redirect("/reports")

    report_data = build_session_report_data(session_id)

    if report_data is None:
        flash("Session report not found.", "error")
        return redirect("/reports")

    return render_template(
        "session_report.html",
        current_session=report_data["current_session"],
        course=report_data["course"],
        students=report_data["students"],
        total_students=report_data["total_students"],
        total_present=report_data["total_present"],
        total_excused=report_data["total_excused"],
        total_absent=report_data["total_absent"],
        attendance_percentage=report_data["attendance_percentage"],
        user_role=session.get("role")
    )
# =========================
# ADMIN - STUDENTS MANAGEMENT
# =========================
@app.route("/admin/students")
def admin_students():

    if not is_admin():
        return redirect("/")

    students_list = fetch_all(
        """
        SELECT 
            student_id,
            university_id,
            full_name,
            email,
            department,
            is_active,
            face_label,
            face_registered
        FROM student
        ORDER BY student_id DESC
        """
    )

    return render_template(
        "students.html",
        students=students_list
    )


@app.route("/admin/students/add", methods=["GET", "POST"])
def add_student():

    if not is_admin():
        return redirect("/")

    error = None

    if request.method == "POST":

        university_id = request.form.get("university_id", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        department = request.form.get("department", "").strip()
        face_label = request.form.get("face_label", "").strip().lower()
        is_active = request.form.get("is_active")

        if is_active == "1":
            is_active = 1
        else:
            is_active = 0

        if not university_id or not full_name or not email or not department or not face_label:
            error = "Please fill in all required fields."

        elif not university_id.isdigit() or len(university_id) != 12:
            error = "University ID must be exactly 12 digits."

        else:
            existing_university_id = fetch_one(
                """
                SELECT student_id
                FROM student
                WHERE university_id = %s
                """,
                (university_id,)
            )

            existing_email = fetch_one(
                """
                SELECT student_id
                FROM student
                WHERE email = %s
                """,
                (email,)
            )

            existing_face_label = fetch_one(
                """
                SELECT student_id
                FROM student
                WHERE face_label = %s
                """,
                (face_label,)
            )

            existing_user = fetch_one(
                """
                SELECT user_id
                FROM users
                WHERE username = %s
                """,
                (university_id,)
            )

            if existing_university_id:
                error = "University ID already exists."

            elif existing_email:
                error = "Email already exists."

            elif existing_face_label:
                error = "Face label already exists."

            elif existing_user:
                error = "A login account already exists for this university ID."

            else:
                new_student_id = execute_query(
                    """
                    INSERT INTO student
                    (university_id, full_name, email, department, is_active, face_label, face_registered)
                    VALUES (%s, %s, %s, %s, %s, %s, 0)
                    """,
                    (
                        university_id,
                        full_name,
                        email,
                        department,
                        is_active,
                        face_label
                    )
                )

                first_name = full_name.split()[0]
                default_password = first_name + university_id[-3:]
                hashed_password = generate_password_hash(default_password)

                execute_query(
                    """
                    INSERT INTO users
                    (username, password_hash, full_name, email, role, student_id, is_active)
                    VALUES (%s, %s, %s, %s, 'student', %s, %s)
                    """,
                    (
                        university_id,
                        hashed_password,
                        full_name,
                        email,
                        new_student_id,
                        is_active
                    )
                )

                flash("Student and login account added successfully.", "success")
                return redirect("/admin/students")

    return render_template(
        "add_student.html",
        error=error
    )


@app.route("/admin/students/edit/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):

    if not is_admin():
        return redirect("/")

    student = fetch_one(
        """
        SELECT 
            student_id,
            university_id,
            full_name,
            email,
            department,
            is_active,
            face_label
        FROM student
        WHERE student_id = %s
        """,
        (student_id,)
    )

    if student is None:
        flash("Student not found.", "error")
        return redirect("/admin/students")

    error = None

    if request.method == "POST":

        university_id = request.form.get("university_id", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        department = request.form.get("department", "").strip()
        face_label = request.form.get("face_label", "").strip().lower()
        is_active = request.form.get("is_active")

        if is_active == "1":
            is_active = 1
        else:
            is_active = 0

        if not university_id or not full_name or not email or not department or not face_label:
            error = "Please fill in all required fields."

        elif not university_id.isdigit() or len(university_id) != 12:
            error = "University ID must be exactly 12 digits."

        else:
            existing_university_id = fetch_one(
                """
                SELECT student_id
                FROM student
                WHERE university_id = %s
                AND student_id <> %s
                """,
                (university_id, student_id)
            )

            existing_email = fetch_one(
                """
                SELECT student_id
                FROM student
                WHERE email = %s
                AND student_id <> %s
                """,
                (email, student_id)
            )

            existing_face_label = fetch_one(
                """
                SELECT student_id
                FROM student
                WHERE face_label = %s
                AND student_id <> %s
                """,
                (face_label, student_id)
            )

            existing_user = fetch_one(
                """
                SELECT user_id
                FROM users
                WHERE username = %s
                AND (
                    student_id <> %s
                    OR student_id IS NULL
                )
                """,
                (university_id, student_id)
            )

            if existing_university_id:
                error = "University ID already exists."

            elif existing_email:
                error = "Email already exists."

            elif existing_face_label:
                error = "Face label already exists."

            elif existing_user:
                error = "A login account already exists for this university ID."

            else:
                execute_query(
                    """
                    UPDATE student
                    SET university_id = %s,
                        full_name = %s,
                        email = %s,
                        department = %s,
                        is_active = %s,
                        face_label = %s
                    WHERE student_id = %s
                    """,
                    (
                        university_id,
                        full_name,
                        email,
                        department,
                        is_active,
                        face_label,
                        student_id
                    )
                )

                student_user = fetch_one(
                    """
                    SELECT user_id
                    FROM users
                    WHERE student_id = %s
                    AND role = 'student'
                    """,
                    (student_id,)
                )

                if student_user:
                    execute_query(
                        """
                        UPDATE users
                        SET username = %s,
                            full_name = %s,
                            email = %s,
                            is_active = %s
                        WHERE student_id = %s
                        AND role = 'student'
                        """,
                        (
                            university_id,
                            full_name,
                            email,
                            is_active,
                            student_id
                        )
                    )

                else:
                    first_name = full_name.split()[0]
                    default_password = first_name + university_id[-3:]
                    hashed_password = generate_password_hash(default_password)

                    execute_query(
                        """
                        INSERT INTO users
                        (username, password_hash, full_name, email, role, student_id, is_active)
                        VALUES (%s, %s, %s, %s, 'student', %s, %s)
                        """,
                        (
                            university_id,
                            hashed_password,
                            full_name,
                            email,
                            student_id,
                            is_active
                        )
                    )

                flash("Student and login account updated successfully.", "success")
                return redirect("/admin/students")

    return render_template(
        "edit_student.html",
        student=student,
        error=error
    )


@app.route("/admin/students/deactivate/<int:student_id>")
def deactivate_student(student_id):

    if not is_admin():
        return redirect("/")

    student = fetch_one(
        """
        SELECT student_id
        FROM student
        WHERE student_id = %s
        """,
        (student_id,)
    )

    if not student:
        flash("Student not found.", "error")
        return redirect("/admin/students")

    execute_query(
        """
        UPDATE student
        SET is_active = 0
        WHERE student_id = %s
        """,
        (student_id,)
    )

    execute_query(
        """
        UPDATE users
        SET is_active = 0
        WHERE student_id = %s
        AND role = 'student'
        """,
        (student_id,)
    )

    flash("Student and login account deactivated successfully.", "success")
    return redirect("/admin/students")


@app.route("/admin/students/activate/<int:student_id>")
def activate_student(student_id):

    if not is_admin():
        return redirect("/")

    student = fetch_one(
        """
        SELECT student_id
        FROM student
        WHERE student_id = %s
        """,
        (student_id,)
    )

    if not student:
        flash("Student not found.", "error")
        return redirect("/admin/students")

    execute_query(
        """
        UPDATE student
        SET is_active = 1
        WHERE student_id = %s
        """,
        (student_id,)
    )

    execute_query(
        """
        UPDATE users
        SET is_active = 1
        WHERE student_id = %s
        AND role = 'student'
        """,
        (student_id,)
    )

    flash("Student and login account activated successfully.", "success")
    return redirect("/admin/students")
@app.route("/admin/students/<int:student_id>/sections", methods=["GET", "POST"])
def assign_student_sections(student_id):

    if not is_admin():
        return redirect("/")

    student = fetch_one(
        """
        SELECT 
            student_id,
            university_id,
            full_name,
            email,
            department,
            face_label,
            is_active
        FROM student
        WHERE student_id = %s
        """,
        (student_id,)
    )

    if student is None:
        flash("Student not found.", "error")
        return redirect("/admin/students")

    all_sections = fetch_all(
        """
        SELECT
            `section`.section_id,
            course.course_name,
            users.full_name AS instructor_name,
            `section`.room_id,
            `section`.semester,
            `section`.day_of_week,
            `section`.start_time,
            `section`.end_time
        FROM `section`
        JOIN course 
            ON `section`.course_id = course.course_id
        JOIN users
            ON `section`.lecturer_id = users.user_id
        ORDER BY course.course_name, `section`.section_id
        """
    )

    for sec in all_sections:
        sec["start_time"] = format_time_value(sec["start_time"])
        sec["end_time"] = format_time_value(sec["end_time"])

    valid_section_ids = set(
        str(sec["section_id"]) for sec in all_sections
    )

    current_sections = fetch_all(
        """
        SELECT section_id
        FROM section_students
        WHERE student_id = %s
        """,
        (student_id,)
    )

    selected_section_ids = [
        str(row["section_id"]) for row in current_sections
    ]

    if request.method == "POST":

        posted_section_ids = request.form.getlist("section_ids")

        # Remove duplicate section IDs while keeping only valid existing sections
        new_section_ids = []

        for section_id in posted_section_ids:
            if section_id in valid_section_ids and section_id not in new_section_ids:
                new_section_ids.append(section_id)

        execute_query(
            """
            DELETE FROM section_students
            WHERE student_id = %s
            """,
            (student_id,)
        )

        for section_id in new_section_ids:
            execute_query(
                """
                INSERT INTO section_students
                (section_id, student_id)
                VALUES (%s, %s)
                """,
                (section_id, student_id)
            )

        flash("Student sections updated successfully.", "success")
        return redirect("/admin/students")

    return render_template(
        "assign_student_sections.html",
        student=student,
        sections=all_sections,
        selected_section_ids=selected_section_ids
    )


@app.route("/admin/students/register-face/<int:student_id>")
def register_student_face(student_id):

    if not is_admin():
        return redirect("/")

    student = fetch_one(
        """
        SELECT 
            student_id,
            full_name,
            face_label,
            is_active,
            face_registered
        FROM student
        WHERE student_id = %s
        """,
        (student_id,)
    )

    if student is None:
        flash("Student not found.", "error")
        return redirect("/admin/students")

    if student["is_active"] != 1:
        flash("Cannot register face for an inactive student.", "error")
        return redirect("/admin/students")

    if not student["face_label"]:
        flash("Cannot register face because this student has no face label.", "error")
        return redirect("/admin/students")

    try:
        response = requests.post(
            MODEL_REGISTRATION_URL,
            json={
                "student_id": student["student_id"],
                "full_name": student["full_name"],
                "face_label": student["face_label"]
            },
            timeout=120
        )

        try:
            result = response.json()
        except ValueError:
            result = {}

        print("Face Registration Status:", response.status_code)
        print("Face Registration Response:", result)

        if response.status_code == 200 and result.get("success"):

            execute_query(
                """
                UPDATE student
                SET face_registered = 1
                WHERE student_id = %s
                """,
                (student_id,)
            )

            if student["face_registered"] == 1:
                flash("Face updated successfully.", "success")
            else:
                flash("Face registered successfully.", "success")

        else:
            flash(result.get("message", "Face registration failed."), "error")

    except requests.exceptions.Timeout:
        flash("Face registration took too long. Please try again.", "error")

    except requests.exceptions.ConnectionError:
        flash("Could not connect to face registration service. Make sure it is running.", "error")

    except Exception as e:
        print("Error connecting to face registration service:", e)
        flash("Unexpected error occurred during face registration.", "error")

    return redirect("/admin/students")
# =========================
# STUDENT ABSENCE CHECK
# =========================
@app.route("/student-absence", methods=["GET", "POST"])
def student_absence():

    if not is_instructor():
        return redirect("/")

    instructor_courses = get_instructor_courses()

    result = None
    error = None

    selected_section_id = request.form.get("section_id", "").strip()
    university_id = request.form.get("university_id", "").strip()

    if request.method == "POST":

        if not selected_section_id:
            error = "Please choose a course/section."

        elif not university_id:
            error = "Please enter the student university ID."

        else:
            try:
                selected_section_id_int = int(selected_section_id)
            except ValueError:
                error = "Invalid section selected."
                selected_section_id_int = None

            if selected_section_id_int is not None:

                instructor_section_ids = [
                    c["id"] for c in instructor_courses
                ]

                if selected_section_id_int not in instructor_section_ids:
                    error = "You are not allowed to view this section."

                else:
                    student = fetch_one(
                        """
                        SELECT
                            student_id,
                            university_id,
                            full_name,
                            department
                        FROM student
                        WHERE university_id = %s
                        AND is_active = 1
                        """,
                        (university_id,)
                    )

                    if not student:
                        error = "Student not found."

                    else:
                        enrollment = fetch_one(
                            """
                            SELECT enrollment_id
                            FROM section_students
                            WHERE student_id = %s
                            AND section_id = %s
                            """,
                            (
                                student["student_id"],
                                selected_section_id_int
                            )
                        )

                        if not enrollment:
                            error = "This student is not registered in the selected section."

                        else:
                            course = fetch_one(
                                """
                                SELECT
                                    course.course_name,
                                    CONCAT('Section ', `section`.section_id) AS section_name
                                FROM `section`
                                JOIN course
                                    ON `section`.course_id = course.course_id
                                WHERE `section`.section_id = %s
                                """,
                                (selected_section_id_int,)
                            )

                            sessions = fetch_all(
                                """
                                SELECT
                                    session_id,
                                    session_date,
                                    start_time,
                                    end_time
                                FROM `session`
                                WHERE section_id = %s
                                AND is_active = 0
                                ORDER BY session_date
                                """,
                                (selected_section_id_int,)
                            )

                            present_rows = fetch_all(
                                """
                                SELECT
                                    session_id
                                FROM attendance
                                WHERE student_id = %s
                                AND status = 'Present'
                                """,
                                (student["student_id"],)
                            )

                            present_session_ids = set(
                                row["session_id"] for row in present_rows
                            )

                            approved_excuses = fetch_all(
                                """
                                SELECT
                                    session_id,
                                    excuse_date
                                FROM excuse_request
                                WHERE student_id = %s
                                AND section_id = %s
                                AND status = 'approved'
                                """,
                                (
                                    student["student_id"],
                                    selected_section_id_int
                                )
                            )

                            excused_session_ids = set()

                            for excuse in approved_excuses:
                                for s in sessions:

                                    same_session = (
                                        excuse["session_id"] is not None
                                        and excuse["session_id"] == s["session_id"]
                                    )

                                    same_date = (
                                        excuse["session_id"] is None
                                        and excuse["excuse_date"] == s["session_date"]
                                    )

                                    if same_session or same_date:
                                        excused_session_ids.add(s["session_id"])

                            absent_dates = []

                            for s in sessions:
                                session_id = s["session_id"]

                                if session_id not in present_session_ids and session_id not in excused_session_ids:
                                    absent_dates.append({
                                        "session_id": session_id,
                                        "session_date": s["session_date"],
                                        "start_time": format_time_value(s["start_time"]),
                                        "end_time": format_time_value(s["end_time"])
                                    })

                            total_sessions = len(sessions)
                            present_count = len([
                                s for s in sessions
                                if s["session_id"] in present_session_ids
                            ])
                            excused_count = len([
                                s for s in sessions
                                if s["session_id"] in excused_session_ids
                                and s["session_id"] not in present_session_ids
                            ])
                            absent_count = len(absent_dates)

                            if total_sessions > 0:
                                absence_percentage = int((absent_count / total_sessions) * 100)
                            else:
                                absence_percentage = 0

                            result = {
                                "student": student,
                                "course": course,
                                "total_sessions": total_sessions,
                                "present_count": present_count,
                                "excused_count": excused_count,
                                "absent_count": absent_count,
                                "absence_percentage": absence_percentage,
                                "absent_dates": absent_dates
                            }

    return render_template(
        "student_absence.html",
        instructor_courses=instructor_courses,
        result=result,
        error=error,
        selected_section_id=selected_section_id,
        university_id=university_id
    )
@app.route("/api/section-students/<int:section_id>")
def api_section_students(section_id):

    if not is_instructor():
        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    if section_id == 1:
        return jsonify({
            "success": False,
            "message": "This section is for testing only."
        }), 403

    instructor_section_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if section_id not in instructor_section_ids:
        return jsonify({
            "success": False,
            "message": "You are not allowed to view this section."
        }), 403

    students = fetch_all(
        """
        SELECT
            student.student_id,
            student.university_id,
            student.full_name,
            student.department
        FROM section_students
        JOIN student
            ON section_students.student_id = student.student_id
        WHERE section_students.section_id = %s
        AND student.is_active = 1
        ORDER BY student.full_name
        """,
        (section_id,)
    )

    return jsonify({
        "success": True,
        "students": students
    }), 200
# =========================
# INSTRUCTOR SNAPSHOTS
# =========================
def get_instructor_snapshot_sections():
    return get_instructor_courses()


def find_private_snapshots(section_id=None, snapshot_date=None):
    """
    Reads classroom snapshot JSON files from private_uploads/live-result
    and returns only records matching the selected section/date.
    """
    snapshots = []

    if not os.path.isdir(SNAPSHOT_PRIVATE_DIR):
        return snapshots

    section_folder = f"Section_{section_id}" if section_id else None

    for root, dirs, files in os.walk(SNAPSHOT_PRIVATE_DIR):
        if section_folder and section_folder not in root:
            continue

        for filename in files:
            if not filename.lower().endswith(".json"):
                continue

            json_path = os.path.join(root, filename)

            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception:
                continue

            metadata_section_id = str(metadata.get("section_id", ""))
            metadata_date = str(metadata.get("date", ""))

            if section_id and metadata_section_id != str(section_id):
                continue

            if snapshot_date and metadata_date != str(snapshot_date):
                continue

            image_file = metadata.get("image_file")

            if not image_file:
                continue

            image_path = os.path.join(root, image_file)

            if not os.path.exists(image_path):
                continue

            relative_image_path = os.path.relpath(
                image_path,
                SNAPSHOT_PRIVATE_DIR
            ).replace(os.sep, "/")

            metadata["secure_image_url"] = f"/secure-snapshot/{relative_image_path}"
            metadata["relative_image_path"] = relative_image_path

            snapshots.append(metadata)

    snapshots.sort(
        key=lambda item: (
            str(item.get("date", "")),
            str(item.get("time", ""))
        ),
        reverse=True
    )

    return snapshots


@app.route("/instructor-snapshots")
def instructor_snapshots():

    if not is_instructor():
        return redirect("/")

    instructor_id = session.get("user_id")

    sections = get_instructor_snapshot_sections()
    section_ids = [c["id"] for c in sections]

    selected_section_id = request.args.get("section_id", type=int)
    selected_date = request.args.get("snapshot_date", "").strip()

    if not selected_date:
        selected_date = datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")

    snapshots = []

    if selected_section_id:
        if selected_section_id not in section_ids:
            flash("You are not allowed to view snapshots for this section.", "error")
            return redirect("/instructor-snapshots")

        snapshots = find_private_snapshots(
            section_id=selected_section_id,
            snapshot_date=selected_date
        )

    return render_template(
        "instructor_snapshots.html",
        sections=sections,
        snapshots=snapshots,
        selected_section_id=selected_section_id,
        selected_date=selected_date,
        instructor_id=instructor_id
    )


@app.route("/secure-snapshot/<path:relative_path>")
def secure_snapshot(relative_path):
    """
    Protected access to classroom snapshot images.
    Snapshot images are stored outside /static and are only served after checking
    that the current instructor owns the session's section.
    """
    if not is_instructor():
        abort(403)

    safe_path = os.path.normpath(relative_path)

    if safe_path.startswith("..") or os.path.isabs(safe_path):
        abort(400)

    full_path = os.path.abspath(os.path.join(SNAPSHOT_PRIVATE_DIR, safe_path))
    snapshot_root = os.path.abspath(SNAPSHOT_PRIVATE_DIR)

    if not full_path.startswith(snapshot_root + os.sep):
        abort(400)

    if not os.path.exists(full_path):
        abort(404)

    session_match = re.search(r"Session_(\d+)", safe_path.replace("\\", "/"))

    if not session_match:
        abort(403)

    snapshot_session_id = int(session_match.group(1))

    allowed_session = fetch_one(
        """
        SELECT
            `session`.session_id
        FROM `session`
        JOIN `section`
            ON `session`.section_id = `section`.section_id
        WHERE `session`.session_id = %s
        AND `section`.lecturer_id = %s
        """,
        (
            snapshot_session_id,
            session.get("user_id")
        )
    )

    if not allowed_session:
        abort(403)

    return send_file(full_path, as_attachment=False)


# =========================
# INSTRUCTOR EXCUSES
# =========================
@app.route("/instructor-excuses")
def instructor_excuses():

    if not is_instructor():
        return redirect("/")

    instructor_id = session.get("user_id")

    excuses = fetch_all(
        """
        SELECT
            excuse_request.excuse_id,
            excuse_request.excuse_date,
            excuse_request.reason,
            excuse_request.file_path,
            excuse_request.status,
            excuse_request.instructor_note,
            excuse_request.submitted_at,
            excuse_request.reviewed_at,

            student.full_name AS student_name,
            student.university_id,

            course.course_name,
            `section`.section_id

        FROM excuse_request

        JOIN student
            ON excuse_request.student_id = student.student_id

        JOIN `section`
            ON excuse_request.section_id = `section`.section_id

        JOIN course
            ON `section`.course_id = course.course_id

        WHERE `section`.lecturer_id = %s

        ORDER BY
            FIELD(excuse_request.status, 'pending', 'approved', 'rejected'),
            excuse_request.submitted_at DESC
        """,
        (instructor_id,)
    )

    for excuse in excuses:
        if excuse.get("file_path"):
            excuse["secure_file_url"] = f"/secure-excuse/{excuse['excuse_id']}"
        else:
            excuse["secure_file_url"] = None

    return render_template(
        "instructor_excuses.html",
        excuses=excuses
    )



@app.route("/secure-excuse/<int:excuse_id>")
def secure_excuse(excuse_id):
    """
    Protected access to excuse attachments.
    The file is not served from /static. It is returned only after permission checks.
    """
    if session.get("role") not in ["admin", "instructor", "student"]:
        abort(403)

    excuse = fetch_one(
        """
        SELECT
            excuse_request.excuse_id,
            excuse_request.student_id,
            excuse_request.file_path,
            `section`.lecturer_id
        FROM excuse_request
        JOIN `section`
            ON excuse_request.section_id = `section`.section_id
        WHERE excuse_request.excuse_id = %s
        """,
        (excuse_id,)
    )

    if not excuse or not excuse.get("file_path"):
        abort(404)

    allowed = False

    if is_admin():
        allowed = True

    elif is_instructor() and excuse["lecturer_id"] == session.get("user_id"):
        allowed = True

    elif is_student() and excuse["student_id"] == session.get("student_id"):
        allowed = True

    if not allowed:
        abort(403)

    file_path = build_private_excuse_file_path(excuse["file_path"])

    if not file_path or not os.path.exists(file_path):
        abort(404)

    return send_file(file_path, as_attachment=False)


@app.route("/excuses/<int:excuse_id>/approve", methods=["POST"])
def approve_excuse(excuse_id):

    if not is_instructor():
        return redirect("/")

    instructor_id = session.get("user_id")
    instructor_note = request.form.get("instructor_note", "").strip()

    allowed_excuse = fetch_one(
        """
        SELECT
            excuse_request.excuse_id,
            excuse_request.status
        FROM excuse_request
        JOIN `section`
            ON excuse_request.section_id = `section`.section_id
        WHERE excuse_request.excuse_id = %s
        AND `section`.lecturer_id = %s
        """,
        (excuse_id, instructor_id)
    )

    if not allowed_excuse:
        flash("Excuse request not found or you are not allowed to review it.", "error")
        return redirect("/instructor-excuses")

    if allowed_excuse["status"] != "pending":
        flash("This excuse request has already been reviewed.", "info")
        return redirect("/instructor-excuses")

    execute_query(
        """
        UPDATE excuse_request
        SET status = 'approved',
            instructor_note = %s,
            reviewed_at = NOW()
        WHERE excuse_id = %s
        AND status = 'pending'
        """,
        (instructor_note, excuse_id)
    )

    flash("Excuse approved successfully.", "success")
    return redirect("/instructor-excuses")


@app.route("/excuses/<int:excuse_id>/reject", methods=["POST"])
def reject_excuse(excuse_id):

    if not is_instructor():
        return redirect("/")

    instructor_id = session.get("user_id")
    instructor_note = request.form.get("instructor_note", "").strip()

    allowed_excuse = fetch_one(
        """
        SELECT
            excuse_request.excuse_id,
            excuse_request.status
        FROM excuse_request
        JOIN `section`
            ON excuse_request.section_id = `section`.section_id
        WHERE excuse_request.excuse_id = %s
        AND `section`.lecturer_id = %s
        """,
        (excuse_id, instructor_id)
    )

    if not allowed_excuse:
        flash("Excuse request not found or you are not allowed to review it.", "error")
        return redirect("/instructor-excuses")

    if allowed_excuse["status"] != "pending":
        flash("This excuse request has already been reviewed.", "info")
        return redirect("/instructor-excuses")

    execute_query(
        """
        UPDATE excuse_request
        SET status = 'rejected',
            instructor_note = %s,
            reviewed_at = NOW()
        WHERE excuse_id = %s
        AND status = 'pending'
        """,
        (instructor_note, excuse_id)
    )

    flash("Excuse rejected.", "success")
    return redirect("/instructor-excuses")
# =========================
# PDF EXPORT
# =========================
@app.route("/export-session-report-pdf/<int:session_id>")
def export_session_report_pdf(session_id):

    if session.get("role") not in ["admin", "instructor"]:
        return redirect("/")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        flash("Session not found.", "error")
        return redirect("/reports")

    if is_instructor():
        instructor_section_ids = [
            c["id"] for c in get_instructor_courses()
        ]

        if current_session["course_id"] not in instructor_section_ids:
            flash("You are not allowed to export this session report.", "error")
            return redirect("/reports")

    report_data = build_session_report_data(session_id)

    if report_data is None:
        flash("Session report not found.", "error")
        return redirect("/reports")

    buffer = BytesIO()
    p = canvas.Canvas(buffer)

    y = 800
    course = report_data["course"]

    # =========================
    # HEADER
    # =========================
    p.setFont("Helvetica-Bold", 16)
    p.drawString(170, y, "Session Attendance Report")
    y -= 40

    p.setFont("Helvetica", 12)
    p.drawString(50, y, f"Session ID: {report_data['current_session']['session_id']}")
    y -= 20

    if course:
        p.drawString(50, y, f"Course: {course['name']} - {course['section']}")
        y -= 20

    p.drawString(50, y, f"Status: {report_data['current_session']['status']}")
    y -= 20

    p.drawString(50, y, f"Total Students: {report_data['total_students']}")
    y -= 20

    p.drawString(50, y, f"Present: {report_data['total_present']}")
    y -= 20

    p.drawString(50, y, f"Excused: {report_data.get('total_excused', 0)}")
    y -= 20

    p.drawString(50, y, f"Absent: {report_data['total_absent']}")
    y -= 20

    p.drawString(50, y, f"Attendance Rate: {report_data['attendance_percentage']}%")
    y -= 40

    # =========================
    # TABLE HEADER
    # =========================
    p.setFont("Helvetica-Bold", 13)
    p.drawString(50, y, "Students Attendance")
    y -= 25

    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Student ID")
    p.drawString(150, y, "Name")
    p.drawString(320, y, "Department")
    p.drawString(430, y, "Status")
    y -= 15

    p.setFont("Helvetica", 10)

    for s in report_data["students"]:

        if y < 80:
            p.showPage()
            y = 800

            p.setFont("Helvetica-Bold", 13)
            p.drawString(50, y, "Students Attendance - Continued")
            y -= 25

            p.setFont("Helvetica-Bold", 10)
            p.drawString(50, y, "Student ID")
            p.drawString(150, y, "Name")
            p.drawString(320, y, "Department")
            p.drawString(430, y, "Status")
            y -= 15

            p.setFont("Helvetica", 10)

        p.drawString(50, y, str(s["id"]))
        p.drawString(150, y, str(s["name"])[:25])
        p.drawString(320, y, str(s["dept"])[:15])
        p.drawString(430, y, str(s["status"]))
        y -= 18

    p.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"session_{session_id}_report.pdf",
        mimetype="application/pdf"
    )

# =========================
# API
# =========================
@app.route("/api/mark-attendance", methods=["POST"])
def api_mark_attendance():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "No JSON data received"
        }), 400

    session_id = data.get("session_id")
    student_id = data.get("student_id")
    university_id = data.get("university_id")
    name = data.get("name")

    if not session_id:
        return jsonify({
            "success": False,
            "message": "session_id is required"
        }), 400

    try:
        session_id = int(session_id)
    except ValueError:
        return jsonify({
            "success": False,
            "message": "Invalid session_id"
        }), 400

    current_session = get_session_by_id(session_id)

    if current_session is None:
        return jsonify({
            "success": False,
            "message": "Session not found"
        }), 404

    if current_session["status"] != "active":
        return jsonify({
            "success": False,
            "message": "Session is closed"
        }), 400

    if student_id:
        try:
            student_id = int(student_id)
        except ValueError:
            return jsonify({
                "success": False,
                "message": "Invalid student_id"
            }), 400

    if not student_id and university_id:
        student = fetch_one(
            """
            SELECT student_id
            FROM student
            WHERE university_id = %s
            AND is_active = 1
            """,
            (university_id,)
        )

        if student:
            student_id = student["student_id"]

    if not student_id and name:
        student = fetch_one(
            """
            SELECT student_id
            FROM student
            WHERE is_active = 1
            AND (
                LOWER(face_label) = LOWER(%s)
                OR LOWER(full_name) = LOWER(%s)
            )
            """,
            (name, name)
        )

        if student:
            student_id = student["student_id"]

    if not student_id:
        return jsonify({
            "success": False,
            "message": "student_id, university_id, or name is required"
        }), 400

    active_student = fetch_one(
        """
        SELECT student_id
        FROM student
        WHERE student_id = %s
        AND is_active = 1
        """,
        (student_id,)
    )

    if not active_student:
        return jsonify({
            "success": False,
            "message": "Student not found or inactive"
        }), 404

    allowed_student = fetch_one(
        """
        SELECT student_id
        FROM section_students
        WHERE section_id = %s
        AND student_id = %s
        """,
        (current_session["course_id"], student_id)
    )

    if allowed_student is None:
        return jsonify({
            "success": False,
            "message": "Student does not belong to this section"
        }), 403

    already_marked = fetch_one(
        """
        SELECT attendance_id
        FROM attendance
        WHERE session_id = %s
        AND student_id = %s
        """,
        (session_id, student_id)
    )

    if already_marked:
        return jsonify({
            "success": True,
            "message": "Student already marked as present",
            "student_id": student_id,
            "session_id": session_id
        }), 200

    execute_query(
        """
        INSERT INTO attendance
        (session_id, student_id, status, recognition_time)
        VALUES (%s, %s, %s, NOW())
        """,
        (session_id, student_id, "Present")
    )

    return jsonify({
        "success": True,
        "message": "Attendance recorded successfully",
        "student_id": student_id,
        "session_id": session_id
    }), 201


@app.route("/api/dashboard-data")
def dashboard_data():

    if session.get("role") not in ["admin", "instructor"]:
        return jsonify({
            "success": False,
            "message": "Unauthorized"
        }), 401

    students_count = fetch_one("SELECT COUNT(*) AS total FROM student WHERE is_active = 1")
    courses_count = fetch_one("SELECT COUNT(*) AS total FROM course")
    sessions_count = fetch_one("SELECT COUNT(*) AS total FROM `session`")
    attendance_count = fetch_one("SELECT COUNT(*) AS total FROM attendance")

    return jsonify({
        "success": True,
        "students": students_count["total"],
        "courses": courses_count["total"],
        "sessions": sessions_count["total"],
        "attendance": attendance_count["total"]
    }), 200

@app.route("/api/end-active-session", methods=["POST"])
def api_end_active_session():

    data = request.get_json(silent=True) or {}

    session_id = data.get("session_id")

    if not session_id:
        return jsonify({
            "success": False,
            "message": "Missing session_id"
        }), 400

    current_session = fetch_one(
        """
        SELECT session_id, is_active
        FROM `session`
        WHERE session_id = %s
        """,
        (session_id,)
    )

    if current_session is None:
        return jsonify({
            "success": False,
            "message": "Session not found"
        }), 404

    if current_session["is_active"] == 0:
        return jsonify({
            "success": True,
            "message": "Session already closed"
        }), 200

    execute_query(
        """
        UPDATE `session`
        SET is_active = 0
        WHERE session_id = %s
        """,
        (session_id,)
    )

    return jsonify({
        "success": True,
        "message": "Session ended successfully"
    }), 200

@app.route("/api/active-session")
def api_active_session():

    active_session = fetch_one(
        """
        SELECT
        `session`.session_id,
        `session`.section_id,
        `session`.session_date,
        `session`.start_time,
        `session`.end_time,
        course.course_id,
        course.course_name
    FROM `session`
    JOIN `section`
        ON `session`.section_id = `section`.section_id
    JOIN course
        ON `section`.course_id = course.course_id
    WHERE `session`.is_active = 1
    ORDER BY `session`.session_id DESC
    LIMIT 1
    """
    )

    if active_session is None:
        return jsonify({
            "success": False,
            "message": "No active session found"
        }), 404

    section_students = fetch_all(
        """
        SELECT
            student.student_id,
            student.full_name,
            student.face_label
        FROM section_students
        JOIN student
            ON section_students.student_id = student.student_id
        WHERE section_students.section_id = %s
        AND student.is_active = 1
        AND student.face_label IS NOT NULL
        AND student.face_label <> ''
        ORDER BY student.full_name
        """,
        (active_session["section_id"],)
    )

    allowed_face_labels = []

    for student in section_students:
        allowed_face_labels.append(student["face_label"])

    return jsonify({
      "success": True,
      "session_id": active_session["session_id"],
      "section_id": active_session["section_id"],
      "course_id": active_session["course_id"],
      "course_name": active_session["course_name"],
      "session_date": str(active_session["session_date"]),
      "start_time": str(active_session["start_time"]),
      "end_time": str(active_session["end_time"]),
      "allowed_face_labels": allowed_face_labels,
      "students": section_students
    }), 200


@app.route("/api/face-labels")
def api_face_labels():

    students = fetch_all(
        """
        SELECT
            student_id,
            full_name,
            face_label
        FROM student
        WHERE face_label IS NOT NULL
        AND face_label <> ''
        AND is_active = 1
        ORDER BY student_id
        """
    )

    labels = []

    for student in students:
        labels.append({
            "student_id": student["student_id"],
            "full_name": student["full_name"],
            "face_label": student["face_label"]
        })

    return jsonify({
        "success": True,
        "labels": labels
    }), 200


# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
