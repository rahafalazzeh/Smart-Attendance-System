from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime
import mysql.connector
from db_config import DB_CONFIG

app = Flask(__name__)
app.secret_key = "secret-key"


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
# TEMPORARY DATA
# لاحقًا سنستبدلها كلها بالداتا بيز
# =========================

students = [
    {"id": "12001", "name": "Ahmad Ali", "dept": "CS"},
    {"id": "12002", "name": "Sara Mohamed", "dept": "IT"},
    {"id": "12003", "name": "Omar Khaled", "dept": "CS"},
]

courses = [
    {
        "id": 1,
        "name": "Web Development",
        "section": "A",
        "instructor_username": "instructor",
        "day": "Wednesday",
        "start_time": "08:00",
        "end_time": "12:00"
    },
    {
        "id": 2,
        "name": "Computer Networks",
        "section": "B",
        "instructor_username": "instructor",
        "day": "Wednesday",
        "start_time": "08:00",
        "end_time": "12:00"
    },
]

course_students = {
    1: ["12001", "12002"],
    2: ["12002", "12003"],
}

sessions = []
attendance = []


# =========================
# HELPERS
# =========================

def is_admin():
    return session.get("role") == "admin"


def is_instructor():
    return session.get("role") == "instructor"


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


def get_started_by_value():
    """
    Database has admin_user table.
    If session.started_by is linked to admin_user, use first admin_user id.
    If not found, use current logged-in user_id.
    """
    admin_user = fetch_one(
        """
        SELECT user_id
        FROM admin_user
        ORDER BY user_id
        LIMIT 1
        """
    )

    if admin_user:
        return admin_user["user_id"]

    return session.get("user_id")


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
        ORDER BY student.full_name
        """,
        (section_id,)
    )


def is_course_active_now(course):
    now = datetime.now()

    current_day_short = now.strftime("%a")
    current_day_full = now.strftime("%A")
    current_time = now.strftime("%H:%M")

    # تنظيف شكل الأيام القادمة من الداتا بيز
    days_text = str(course["day"])
    days_text = days_text.replace("{", "")
    days_text = days_text.replace("}", "")
    days_text = days_text.replace("'", "")
    days_text = days_text.replace('"', "")
    days_text = days_text.replace(" ", "")

    course_days = days_text.split(",")

    start_time = format_time_value(course["start_time"])
    end_time = format_time_value(course["end_time"])

    return (
        (current_day_short in course_days or current_day_full in course_days)
        and start_time <= current_time <= end_time
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
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def handle_login():

    username = request.form.get("username")
    password = request.form.get("password")

    user = fetch_one(
        """
        SELECT user_id, username, password_hash, full_name, role
        FROM users
        WHERE username = %s
        AND is_active = 1
        """,
        (username,)
    )

    if user and user["password_hash"] == password:

        if user["role"] == "admin":
            session["role"] = "admin"
            session["username"] = user["username"]
            session["user_id"] = user["user_id"]
            session["full_name"] = user["full_name"]
            return redirect("/admin-dashboard")

        elif user["role"] == "instructor":
            session["role"] = "instructor"
            session["username"] = user["username"]
            session["user_id"] = user["user_id"]
            session["full_name"] = user["full_name"]
            return redirect("/instructor-dashboard")

    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# =========================
# DASHBOARDS
# =========================

@app.route("/admin-dashboard")
def admin_dashboard():

    if not is_admin():
        return redirect("/")

    total_students_result = fetch_one("SELECT COUNT(*) AS total FROM student")
    active_sessions_result = fetch_one("SELECT COUNT(*) AS total FROM `session` WHERE is_active = 1")
    closed_sessions_result = fetch_one("SELECT COUNT(*) AS total FROM `session` WHERE is_active = 0")
    attendance_result = fetch_one("SELECT COUNT(*) AS total FROM attendance")

    return render_template(
        "admin_dashboard.html",
        total_students=total_students_result["total"],
        active_sessions=active_sessions_result["total"],
        closed_sessions=closed_sessions_result["total"],
        total_attendance=attendance_result["total"]
    )


@app.route("/instructor-dashboard")
def instructor_dashboard():

    if not is_instructor():
        return redirect("/")

    instructor_courses = get_instructor_courses()
    instructor_students = get_students_for_courses(instructor_courses)

    active_courses = get_active_courses_now(instructor_courses)

    instructor_sessions = get_sessions_for_courses(instructor_courses)
    instructor_attendance = get_attendance_for_sessions(instructor_sessions)

    last_session = instructor_sessions[0] if instructor_sessions else None

    current_lectures = []

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

        current_lectures.append({
            "course": course,
            "active_session": active_session
        })

    return render_template(
        "instructor_dashboard.html",
        courses=instructor_courses,
        active_courses=active_courses,
        current_lectures=current_lectures,
        total_students=len(instructor_students),
        total_courses=len(instructor_courses),
        total_sessions=len(instructor_sessions),
        total_attendance=len(instructor_attendance),
        last_session=last_session
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
        return redirect("/instructor-dashboard")

    if not is_course_active_now(course):
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
        AND is_active = 1
        ORDER BY session_id DESC
        LIMIT 1
        """,
        (course_id,)
    )

    if existing_session:
        return redirect(f"/attendance/{existing_session['session_id']}")

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
            get_started_by_value()
        )
    )

    return redirect(f"/attendance/{new_session_id}")


@app.route("/end-session/<int:session_id>")
def end_session(session_id):

    if not is_instructor():
        return redirect("/")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        return redirect("/instructor-dashboard")

    instructor_section_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if current_session["course_id"] not in instructor_section_ids:
        return redirect("/instructor-dashboard")

    execute_query(
        """
        UPDATE `session`
        SET is_active = 0
        WHERE session_id = %s
        """,
        (session_id,)
    )

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
        return redirect("/instructor-dashboard")

    instructor_section_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if current_session["course_id"] not in instructor_section_ids:
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
        """,
        (session_id,)
    )

    present_student_ids = set(
        str(a["student_id"]) for a in session_attendance
    )

    present_students = [
        s for s in session_students
        if str(s["id"]) in present_student_ids
    ]

    absent_students = [
        s for s in session_students
        if str(s["id"]) not in present_student_ids
    ]

    total_students = len(session_students)
    total_present = len(present_students)
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
        total_students=total_students,
        total_present=total_present,
        total_absent=total_absent,
        attendance_percentage=attendance_percentage
    )


@app.route("/mark-attendance", methods=["POST"])
def mark_attendance():

    if not is_instructor():
        return redirect("/")

    student_id = request.form.get("student_id")
    session_id = request.form.get("session_id")

    if not student_id or not session_id:
        return redirect("/instructor-dashboard")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        return redirect("/instructor-dashboard")

    if current_session["status"] != "active":
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
        """,
        (session_id,)
    )

    present_student_ids = set(
        str(a["student_id"]) for a in session_attendance
    )

    report_students = []

    for s in session_students:
        if str(s["id"]) in present_student_ids:
            status = "Present"
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
    total_absent = total_students - total_present

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
        "total_absent": total_absent,
        "attendance_percentage": attendance_percentage
    }


@app.route("/reports", methods=["GET", "POST"])
def reports():

    if session.get("role") not in ["admin", "instructor"]:
        return redirect("/")

    selected_course_name = request.form.get("course_name") if request.method == "POST" else ""
    selected_section = request.form.get("section") if request.method == "POST" else ""

    # Admin يرى كل المواد والشعب والجلسات
    if is_admin():
        available_courses = get_all_courses_sections()

        visible_sessions_rows = fetch_all(
            """
            SELECT 
                `session`.session_id,
                `session`.section_id,
                `session`.session_date,
                `session`.start_time,
                `session`.end_time,
                `session`.is_active
            FROM `session`
            ORDER BY `session`.session_date DESC, `session`.start_time DESC
            """
        )

    # Instructor يرى فقط مواده وشعبه وجلساته
    else:
        available_courses = get_instructor_courses()

        instructor_section_ids = [
            c["id"] for c in available_courses
        ]

        if instructor_section_ids:
            placeholders = ",".join(["%s"] * len(instructor_section_ids))

            visible_sessions_rows = fetch_all(
                f"""
                SELECT 
                    `session`.session_id,
                    `session`.section_id,
                    `session`.session_date,
                    `session`.start_time,
                    `session`.end_time,
                    `session`.is_active
                FROM `session`
                WHERE `session`.section_id IN ({placeholders})
                ORDER BY `session`.session_date DESC, `session`.start_time DESC
                """,
                tuple(instructor_section_ids)
            )
        else:
            visible_sessions_rows = []

    visible_sessions = [
        format_session_row(row)
        for row in visible_sessions_rows
    ]

    # أسماء المواد حسب الدور
    course_names = sorted(set(
        c["name"] for c in available_courses
    ))

    # للإنستركتور: الشعب تظهر بعد اختيار المادة فقط
    # للأدمن: الشعب كلها متاحة
    if is_instructor() and selected_course_name:
        sections = sorted(set(
            c["section"] for c in available_courses
            if c["name"] == selected_course_name
        ))
    elif is_admin():
        sections = sorted(set(
            c["section"] for c in available_courses
        ))
    else:
        sections = []

    # فلترة حسب المادة
    if selected_course_name:
        allowed_section_ids = [
            c["id"] for c in available_courses
            if c["name"] == selected_course_name
        ]

        visible_sessions = [
            s for s in visible_sessions
            if s["course_id"] in allowed_section_ids
        ]

    # فلترة حسب الشعبة
    if selected_section:
        allowed_section_ids = [
            c["id"] for c in available_courses
            if c["section"] == selected_section
            and (not selected_course_name or c["name"] == selected_course_name)
        ]

        visible_sessions = [
            s for s in visible_sessions
            if s["course_id"] in allowed_section_ids
        ]

    session_rows = []

    for s in visible_sessions:
        course = get_course(s["course_id"])

        session_rows.append({
            "session_id": s["session_id"],
            "session_date": s["session_date"],
            "course_name": course["name"] if course else "Unknown",
            "section": course["section"] if course else "-",
            "status": s["status"]
        })

    return render_template(
        "reports.html",
        course_names=course_names,
        sections=sections,
        sessions=session_rows,
        selected_course_name=selected_course_name,
        selected_section=selected_section
    )


@app.route("/session-report/<int:session_id>")
def session_report(session_id):

    if session.get("role") not in ["admin", "instructor"]:
        return redirect("/")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        return redirect("/reports")

    # Instructor لا يرى إلا جلساته
    if is_instructor():
        instructor_section_ids = [
            c["id"] for c in get_instructor_courses()
        ]

        if current_session["course_id"] not in instructor_section_ids:
            return redirect("/reports")

    report_data = build_session_report_data(session_id)

    if report_data is None:
        return redirect("/reports")

    return render_template(
        "session_report.html",
        current_session=report_data["current_session"],
        course=report_data["course"],
        students=report_data["students"],
        total_students=report_data["total_students"],
        total_present=report_data["total_present"],
        total_absent=report_data["total_absent"],
        attendance_percentage=report_data["attendance_percentage"],
        user_role=session.get("role")
    )
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

    selected_section_id = request.form.get("section_id") if request.method == "POST" else ""
    university_id = request.form.get("university_id") if request.method == "POST" else ""

    if request.method == "POST":

        if not selected_section_id or not university_id:
            error = "Please choose a course/section and enter the student university ID."

        else:
            selected_section_id = int(selected_section_id)

            instructor_section_ids = [
                c["id"] for c in instructor_courses
            ]

            if selected_section_id not in instructor_section_ids:
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
                    """,
                    (university_id,)
                )

                if student is None:
                    error = "Student not found."

                else:
                    student_in_section = fetch_one(
                        """
                        SELECT student_id
                        FROM section_students
                        WHERE section_id = %s
                        AND student_id = %s
                        """,
                        (selected_section_id, student["student_id"])
                    )

                    if student_in_section is None:
                        error = "This student is not registered in the selected section."

                    else:
                        course = get_course(selected_section_id)

                        total_sessions_row = fetch_one(
                            """
                            SELECT COUNT(*) AS total
                            FROM `session`
                            WHERE section_id = %s
                            AND is_active = 0
                            """,
                            (selected_section_id,)
                        )

                        present_sessions_row = fetch_one(
                            """
                            SELECT COUNT(*) AS total
                            FROM attendance
                            JOIN `session` 
                                ON attendance.session_id = `session`.session_id
                            WHERE `session`.section_id = %s
                            AND `session`.is_active = 0
                            AND attendance.student_id = %s
                            AND attendance.status = 'Present'
                            """,
                            (selected_section_id, student["student_id"])
                        )

                        total_sessions = total_sessions_row["total"]
                        present_count = present_sessions_row["total"]
                        absent_count = total_sessions - present_count

                        if total_sessions > 0:
                            attendance_rate = int((present_count / total_sessions) * 100)
                        else:
                            attendance_rate = 0

                        result = {
                            "student_name": student["full_name"],
                            "university_id": student["university_id"],
                            "department": student["department"],
                            "course_name": course["name"] if course else "Unknown",
                            "section": course["section"] if course else "-",
                            "total_sessions": total_sessions,
                            "present_count": present_count,
                            "absent_count": absent_count,
                            "attendance_rate": attendance_rate
                        }

    return render_template(
        "student_absence.html",
        courses=instructor_courses,
        selected_section_id=selected_section_id,
        university_id=university_id,
        result=result,
        error=error
    )
# =========================
# PDF EXPORT
# =========================

@app.route("/export-session-report-pdf/<int:session_id>")
def export_session_report_pdf(session_id):

    if session.get("role") not in ["admin", "instructor"]:
        return redirect("/")

    current_session = get_session_by_id(session_id)

    if current_session is None:
        return redirect("/reports")

    # Instructor لا يصدّر إلا جلساته
    if is_instructor():
        instructor_section_ids = [
            c["id"] for c in get_instructor_courses()
        ]

        if current_session["course_id"] not in instructor_section_ids:
            return redirect("/reports")

    report_data = build_session_report_data(session_id)

    if report_data is None:
        return redirect("/reports")

    buffer = BytesIO()
    p = canvas.Canvas(buffer)

    y = 800

    course = report_data["course"]

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

    p.drawString(50, y, f"Absent: {report_data['total_absent']}")
    y -= 20

    p.drawString(50, y, f"Attendance Rate: {report_data['attendance_percentage']}%")
    y -= 40

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
        p.drawString(50, y, str(s["id"]))
        p.drawString(150, y, str(s["name"]))
        p.drawString(320, y, str(s["dept"]))
        p.drawString(430, y, str(s["status"]))
        y -= 18

        if y < 80:
            p.showPage()
            y = 800

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

    # If model sends university_id instead of student_id
    if not student_id and university_id:
        student = fetch_one(
            """
            SELECT student_id
            FROM student
            WHERE university_id = %s
            """,
            (university_id,)
        )

        if student:
            student_id = student["student_id"]

    # If model sends student name instead of student_id
    if not student_id and name:
        student = fetch_one(
            """
            SELECT student_id
            FROM student
            WHERE full_name = %s
            """,
            (name,)
        )

        if student:
            student_id = student["student_id"]

    if not student_id:
        return jsonify({
            "success": False,
            "message": "student_id, university_id, or name is required"
        }), 400

    # Check if student belongs to the same section
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

    # Prevent duplicate attendance
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

    students_count = fetch_one("SELECT COUNT(*) AS total FROM student")
    courses_count = fetch_one("SELECT COUNT(*) AS total FROM course")
    sessions_count = fetch_one("SELECT COUNT(*) AS total FROM `session`")
    attendance_count = fetch_one("SELECT COUNT(*) AS total FROM attendance")

    return jsonify({
        "students": students_count["total"],
        "courses": courses_count["total"],
        "sessions": sessions_count["total"],
        "attendance": attendance_count["total"]
    })
# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(debug=True)