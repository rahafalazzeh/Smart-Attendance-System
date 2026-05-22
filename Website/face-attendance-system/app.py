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
# FAKE DATABASE
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

# الطلاب المرتبطين بكل مادة / شعبة
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


def get_course(course_id):
    return next((c for c in courses if c["id"] == course_id), None)


def get_instructor_courses():
    username = session.get("username")

    return [
        c for c in courses
        if c["instructor_username"] == username
    ]


def get_students_for_courses(instructor_courses):
    course_ids = [c["id"] for c in instructor_courses]

    student_ids = set()

    for course_id in course_ids:
        for student_id in course_students.get(course_id, []):
            student_ids.add(student_id)

    return [
        s for s in students
        if s["id"] in student_ids
    ]


def is_course_active_now(course):
    now = datetime.now()

    current_day = now.strftime("%A")
    current_time = now.strftime("%H:%M")

    return (
        course["day"] == current_day
        and course["start_time"] <= current_time <= course["end_time"]
    )


def get_active_courses_now(instructor_courses):
    return [
        c for c in instructor_courses
        if is_course_active_now(c)
    ]


def get_sessions_for_courses(instructor_courses):
    course_ids = [c["id"] for c in instructor_courses]

    return [
        s for s in sessions
        if s["course_id"] in course_ids
    ]


def get_attendance_for_sessions(instructor_sessions):
    session_ids = [str(s["session_id"]) for s in instructor_sessions]

    return [
        a for a in attendance
        if str(a["session_id"]) in session_ids
    ]


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

    print("USERNAME ENTERED:", username)
    print("PASSWORD ENTERED:", password)

    user = fetch_one(
        """
        SELECT user_id, username, password_hash, full_name, role
        FROM users
        WHERE username = %s
        AND is_active = 1
        """,
        (username,)
    )

    print("USER FROM DATABASE:", user)

    if user:
        print("DB PASSWORD:", user["password_hash"])
        print("DB ROLE:", user["role"])

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

    print("LOGIN FAILED")
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

    total_students = len(students)

    active_sessions = len([
        s for s in sessions
        if s["status"] == "active"
    ])

    closed_sessions = len([
        s for s in sessions
        if s["status"] == "closed"
    ])

    total_attendance = len(attendance)

    return render_template(
        "admin_dashboard.html",
        total_students=total_students,
        active_sessions=active_sessions,
        closed_sessions=closed_sessions,
        total_attendance=total_attendance
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

    last_session = instructor_sessions[-1] if instructor_sessions else None

    current_lectures = []

    for course in active_courses:

        active_session = next(
            (
                s for s in sessions
                if s["course_id"] == course["id"]
                and s["status"] == "active"
            ),
            None
        )

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

    existing_active_session = next(
        (
            s for s in sessions
            if s["course_id"] == course_id and s["status"] == "active"
        ),
        None
    )

    if existing_active_session:
        return redirect(f"/attendance/{existing_active_session['session_id']}")

    new_session = {
        "session_id": len(sessions) + 1,
        "course_id": course_id,
        "status": "active"
    }

    sessions.append(new_session)

    return redirect(f"/attendance/{new_session['session_id']}")

@app.route("/end-session/<int:session_id>")
def end_session(session_id):

    if not is_instructor():
        return redirect("/")

    current_session = next(
        (s for s in sessions if s["session_id"] == session_id),
        None
    )

    if current_session is None:
        return redirect("/instructor-dashboard")

    instructor_course_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if current_session["course_id"] not in instructor_course_ids:
        return redirect("/instructor-dashboard")

    current_session["status"] = "closed"

    return redirect(f"/attendance/{session_id}")
# =========================
# ATTENDANCE - LIVE SESSION PAGE
# =========================

@app.route("/attendance/<int:session_id>")
def attendance_page(session_id):

    if not is_instructor():
        return redirect("/")

    current_session = next(
        (s for s in sessions if s["session_id"] == session_id),
        None
    )

    if current_session is None:
        return redirect("/instructor-dashboard")

    course = get_course(current_session["course_id"])

    instructor_course_ids = [
        c["id"] for c in get_instructor_courses()
    ]

    if current_session["course_id"] not in instructor_course_ids:
        return redirect("/instructor-dashboard")

    session_student_ids = course_students.get(current_session["course_id"], [])

    session_students = [
        s for s in students
        if s["id"] in session_student_ids
    ]

    session_attendance = [
        a for a in attendance
        if str(a["session_id"]) == str(session_id)
    ]

    present_student_ids = [
        a["student_id"] for a in session_attendance
    ]

    present_students = [
        s for s in session_students
        if s["id"] in present_student_ids
    ]

    absent_students = [
        s for s in session_students
        if s["id"] not in present_student_ids
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


# هذا route نخليه موجود للمودل لاحقًا
# المودل يقدر يرسل student_id و session_id عليه
@app.route("/mark-attendance", methods=["POST"])
def mark_attendance():

    if not is_instructor():
        return redirect("/")

    student_id = request.form.get("student_id")
    session_id = request.form.get("session_id")

    if not student_id or not session_id:
        return redirect("/instructor-dashboard")

    current_session = next(
        (s for s in sessions if str(s["session_id"]) == str(session_id)),
        None
    )

    if current_session is None:
        return redirect("/instructor-dashboard")

    # لا تسمح بتسجيل حضور بعد إغلاق الجلسة
    if current_session["status"] != "active":
        return redirect(f"/attendance/{session_id}")

    allowed_students = course_students.get(current_session["course_id"], [])

    if student_id not in allowed_students:
        return redirect(f"/attendance/{session_id}")

    already_marked = any(
        a["student_id"] == student_id and str(a["session_id"]) == str(session_id)
        for a in attendance
    )

    if not already_marked:
        attendance.append({
            "student_id": student_id,
            "session_id": session_id,
            "status": "Present"
        })

    return redirect(f"/attendance/{session_id}")
# =========================
# REPORTS
# =========================

def build_session_report_data(session_id):

    current_session = next(
        (s for s in sessions if s["session_id"] == session_id),
        None
    )

    if current_session is None:
        return None

    course = get_course(current_session["course_id"])

    session_student_ids = course_students.get(current_session["course_id"], [])

    session_students = [
        s for s in students
        if s["id"] in session_student_ids
    ]

    session_attendance = [
        a for a in attendance
        if str(a["session_id"]) == str(session_id)
    ]

    present_student_ids = [
        a["student_id"] for a in session_attendance
    ]

    report_students = []

    for s in session_students:
        status = "Present" if s["id"] in present_student_ids else "Absent"

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

    # Admin: يشوف كل المواد وكل الشعب
    if is_admin():
        available_courses = courses
        visible_sessions = sessions

    # Instructor: يشوف مواده وشعبه فقط
    else:
        available_courses = get_instructor_courses()

        instructor_course_ids = [
            c["id"] for c in available_courses
        ]

        visible_sessions = [
            s for s in sessions
            if s["course_id"] in instructor_course_ids
        ]

    # قائمة المواد حسب الدور
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

    # فلترة حسب المادة إذا اختارها المستخدم
    if selected_course_name:
        allowed_course_ids = [
            c["id"] for c in available_courses
            if c["name"] == selected_course_name
        ]

        visible_sessions = [
            s for s in visible_sessions
            if s["course_id"] in allowed_course_ids
        ]

    # فلترة حسب الشعبة إذا اختارها المستخدم
    if selected_section:
        allowed_course_ids = [
            c["id"] for c in available_courses
            if c["section"] == selected_section
            and (not selected_course_name or c["name"] == selected_course_name)
        ]

        visible_sessions = [
            s for s in visible_sessions
            if s["course_id"] in allowed_course_ids
        ]

    session_rows = []

    for s in visible_sessions:
        course = get_course(s["course_id"])

        session_rows.append({
            "session_id": s["session_id"],
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

    current_session = next(
        (s for s in sessions if s["session_id"] == session_id),
        None
    )

    if current_session is None:
        return redirect("/reports")

    # Instructor ما يشوف إلا جلساته
    if is_instructor():
        instructor_course_ids = [
            c["id"] for c in get_instructor_courses()
        ]

        if current_session["course_id"] not in instructor_course_ids:
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
# PDF EXPORT
# =========================

@app.route("/export-session-report-pdf/<int:session_id>")
def export_session_report_pdf(session_id):

    if session.get("role") not in ["admin", "instructor"]:
        return redirect("/")

    current_session = next(
        (s for s in sessions if s["session_id"] == session_id),
        None
    )

    if current_session is None:
        return redirect("/reports")

    # Instructor ما يصدّر إلا جلساته
    if is_instructor():
        instructor_course_ids = [
            c["id"] for c in get_instructor_courses()
        ]

        if current_session["course_id"] not in instructor_course_ids:
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
        p.drawString(50, y, f"Course: {course['name']} - Section {course['section']}")
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

@app.route("/api/dashboard-data")
def dashboard_data():

    return jsonify({
        "students": len(students),
        "courses": len(courses),
        "sessions": len(sessions),
        "attendance": len(attendance)
    })


# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(debug=True)