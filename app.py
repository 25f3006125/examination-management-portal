import os
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Examiner, Course, Examination, ExamAssignment, Rubric, Score, Slot, Booking

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-only-change-me"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "emp.db")

db.init_app(app)

csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def create_admin():
    if User.query.filter_by(role="admin").first() is None:
        admin = User(email="admin@emp.local", name="Administrator", role="admin", password_hash=generate_password_hash("admin123"))
        db.session.add(admin)
        db.session.commit()

with app.app_context():
    db.create_all()
    create_admin()

@app.before_request
def check_access():
    areas = (("/admin", "admin"), ("/examiner", "examiner"), ("/student", "student"))
    for prefix, role in areas:
        if request.path == prefix or request.path.startswith(prefix + "/"):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role != role:
                abort(403) 

@app.route("/")
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    if current_user.role == "examiner":
        return redirect(url_for("examiner_dashboard"))
    return redirect(url_for("student_dashboard"))

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        phone = request.form["phone"]
        department = request.form["department"]
        role = request.form["role"]
        if role not in ("student", "examiner"):
            flash("Please choose Student or Examiner.", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email is already registered.", "danger")
            return redirect(url_for("register"))
        user = User(email=email, name=name, phone=phone, department=department, role=role, password_hash=generate_password_hash(password))
        db.session.add(user)
        if role == "examiner":
            db.session.add(Examiner(user=user))   # status starts as "Pending"
        db.session.commit()
        flash("Successfully registered! Plaese log in. Examiners can log in after the Admin approves them.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user is None or not check_password_hash(user.password_hash, password):
            flash("Incorrect email or password.", "danger")
            return redirect(url_for("login"))
        if user.role == "examiner" and user.profile.status != "Approved":
            flash("Your examiner account is not approved yet.", "warning")
            return redirect(url_for("login"))
        login_user(user)
        return redirect(url_for("home"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/examiner")
def examiner_dashboard():
    return render_template("examiner_dashboard.html")

@app.route("/student")
def student_dashboard():
    return render_template("student_dashboard.html")


#Admin: Dashboard
@app.route("/admin")
def admin_dashboard():
    stats = [
        ("Courses", Course.query.count(), url_for("admin_courses")),
        ("Examinations", Examination.query.count(), url_for("admin_exams")),
        ("Examiners", User.query.filter_by(role="examiner").count(), url_for("admin_examiners")),
        ("Students", User.query.filter_by(role="student").count(), url_for("admin_students")),
        ("Exam slots", Slot.query.count(), None),
        ("Bookings", Booking.query.count(), None),
    ]
    return render_template("admin_dashboard.html", stats=stats)

#Admin: courses
@app.route("/admin/courses")
def admin_courses():
    courses = Course.query.order_by(Course.code).all()
    return render_template("admin_courses.html", courses=courses)

@app.route("/admin/courses/new", methods=["GET", "POST"])
def new_course():
    if request.method == "POST":
        code = request.form["code"].strip().upper()
        name = request.form["name"].strip()
        description = request.form["description"].strip()
        status = request.form["status"]
        if status not in ("Active", "Inactive"):
            flash("Invalid status.", "danger")
            return redirect(url_for("new_course"))
        if Course.query.filter_by(code=code).first():
            flash("That course code already exists.", "danger")
            return redirect(url_for("new_course"))
        db.session.add(Course(code=code, name=name, description=description, status=status))
        db.session.commit()
        flash("Course added.", "success")
        return redirect(url_for("admin_courses"))
    return render_template("course_form.html", course=None)


@app.route("/admin/courses/<int:course_id>/edit", methods=["GET", "POST"])
def edit_course(course_id):
    course = db.get_or_404(Course, course_id)
    if request.method == "POST":
        code = request.form["code"].strip().upper()
        name = request.form["name"].strip()
        description = request.form["description"].strip()
        status = request.form["status"]
        if status not in ("Active", "Inactive"):
            flash("Invalid status.", "danger")
            return redirect(url_for("edit_course", course_id=course.id))
        same_code = Course.query.filter_by(code=code).first()
        if same_code and same_code.id != course.id:
            flash("Another course already uses that code.", "danger")
            return redirect(url_for("edit_course", course_id=course.id))
        course.code = code
        course.name = name
        course.description = description
        course.status = status
        db.session.commit()
        flash("Course updated.", "success")
        return redirect(url_for("admin_courses"))
    return render_template("course_form.html", course=course)


@app.route("/admin/courses/<int:course_id>/delete", methods=["POST"])
def delete_course(course_id):
    course = db.get_or_404(Course, course_id)
    if course.examinations:
        flash("Cannot delete: This course still has examinations. Set it to Inactive instead.", "danger")
    else:
        db.session.delete(course)
        db.session.commit()
        flash("Course deleted.", "success")
    return redirect(url_for("admin_courses"))

#Admin: Examinations
EXAM_TYPES = ["Viva", "Practical", "Project Demo", "Assessment"]

def read_exam_form():
    try:
        values = {
            "course_id": int(request.form["course_id"]),
            "name": request.form["name"].strip(),
            "exam_type": request.form["exam_type"],
            "duration": int(request.form["duration"]),
            "max_marks": int(request.form["max_marks"]),
            "slot_start": date.fromisoformat(request.form["slot_start"]),
            "slot_end": date.fromisoformat(request.form["slot_end"]),
            "booking_start": date.fromisoformat(request.form["booking_start"]),
            "booking_end": date.fromisoformat(request.form["booking_end"]),
        }
    except ValueError:
        return None, "Please fill in every field with valid numbers and dates."
    if db.session.get(Course, values["course_id"]) is None:
        return None, "Please choose a valid course."
    if values["exam_type"] not in EXAM_TYPES:
        return None, "Please choose a valid examination type."
    if values["duration"] < 1 or values["max_marks"] < 1:
        return None, "Duration and maximum marks must be at least 1."
    if values["slot_end"] < values["slot_start"]:
        return None, "Slot creation cannot end before it starts."
    if values["booking_end"] < values["booking_start"]:
        return None, "Booking cannot end before it starts."
    return values, None

@app.route("/admin/exams")
def admin_exams():
    exams = Examination.query.order_by(Examination.id).all()
    return render_template("admin_exams.html", exams=exams, phase=PHASES)

@app.route("/admin/exams/new", methods=["GET", "POST"])
def new_exam():
    courses = Course.query.order_by(Course.code).all()
    if not courses:
        flash("Add a course first, then you can create examinations.", "warning")
        return redirect(url_for("admin_courses"))
    if request.method == "POST":
        values, error = read_exam_form()
        if error:
            flash(error, "danger")
            return redirect(url_for("new_exam"))
        db.session.add(Examination(**values))
        db.session.commit()
        flash("Examination added.", "success")
        return redirect(url_for("admin_exams"))
    return render_template("exam_form.html", exam=None, courses=courses, exam_types=EXAM_TYPES)

@app.route("/admin/exams/<int:exam_id>/edit", methods=["GET", "POST"])
def edit_exam(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    if request.method == "POST":
        values, error = read_exam_form()
        if error:
            flash(error, "danger")
            return redirect(url_for("edit_exam", exam_id=exam.id))
        exam.course_id = values["course_id"]
        exam.name = values["name"]
        exam.exam_type = values["exam_type"]
        exam.duration = values["duration"]
        exam.max_marks = values["max_marks"]
        exam.slot_start = values["slot_start"]
        exam.slot_end = values["slot_end"]
        exam.booking_start = values["booking_start"]
        exam.booking_end = values["booking_end"]
        db.session.commit()
        flash("Examination updated.", "success")
        return redirect(url_for("admin_exams"))
    courses = Course.query.order_by(Course.code).all()
    return render_template("exam_form.html", exam=exam, courses=courses, exam_types=EXAM_TYPES)

@app.route("/admin/exams/<int:exam_id>/delete", methods=["POST"])
def delete_exam(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    if exam.slots:
        flash("Cannot delete: this examination already has slots.", "danger")
    else:
        for rubric in exam.rubrics:
            db.session.delete(rubric)
        for assignment in exam.assignments:
            db.session.delete(assignment)
        db.session.delete(exam)
        db.session.commit()
        flash("Examination deleted.", "success")
    return redirect(url_for("admin_exams"))

#Admin: rubrics
def read_rubric_form(exam, rubric=None):
    try:
        values = {
            "criterion": request.form["criterion"].strip(),
            "max_marks": int(request.form["max_marks"]),
            "weightage": float(request.form["weightage"]),
            "description": request.form["description"].strip(),
        }
    except ValueError:
        return None, "Maximum marks and weightage must be numbers."
    if not values["criterion"]:
        return None, "Criterion name is required."
    if values["max_marks"] < 1:
        return None, "Maximum marks must be at least 1."
    if values["weightage"] < 0 or values["weightage"] > 100:
        return None, "Weightage must be between 0 and 100."
    others = sum(r.max_marks for r in exam.rubrics if rubric is None or r.id != rubric.id)
    new_total = others + values["max_marks"]
    if new_total > exam.max_marks:
        return None, f"Rubric marks would total {new_total}, but this examination has only {exam.max_marks} marks."
    return values, None

@app.route("/admin/exams/<int:exam_id>/rubrics", methods=["GET", "POST"])
def exam_rubrics(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    if request.method == "POST":
        values, error = read_rubric_form(exam)
        if error:
            flash(error, "danger")
        else:
            db.session.add(Rubric(exam_id=exam.id, **values))
            db.session.commit()
            flash("Rubric added.", "success")
        return redirect(url_for("exam_rubrics", exam_id=exam.id))
    total = sum(r.max_marks for r in exam.rubrics)
    return render_template("exam_rubrics.html", exam=exam, total=total)

@app.route("/admin/rubrics/<int:rubric_id>/edit", methods=["GET", "POST"])
def edit_rubric(rubric_id):
    rubric = db.get_or_404(Rubric, rubric_id)
    if request.method == "POST":
        values, error = read_rubric_form(rubric.exam, rubric)
        if error:
            flash(error, "danger")
            return redirect(url_for("edit_rubric", rubric_id=rubric.id))
        rubric.criterion = values["criterion"]
        rubric.max_marks = values["max_marks"]
        rubric.weightage = values["weightage"]
        rubric.description = values["description"]
        db.session.commit()
        flash("Rubric updated.", "success")
        return redirect(url_for("exam_rubrics", exam_id=rubric.exam_id))
    return render_template("rubric_form.html", rubric=rubric)

@app.route("/admin/rubrics/<int:rubric_id>/delete", methods=["POST"])
def delete_rubric(rubric_id):
    rubric = db.get_or_404(Rubric, rubric_id)
    exam_id= rubric.exam_id
    if Score.query.filter_by(rubric_id=rubric.id).first():
        flash("Cannot delete: marks have already been given using this rubric.", "danger")
    else:
        db.session.delete(rubric)
        db.session.commit()
        flash("Rubric deleted.", "success")
    return redirect(url_for("exam_rubrics", exam_id=exam_id))

#Admin: examiners and students
@app.route("/admin/examiners")
def admin_examiners():
    examiners = Examiner.query.order_by(Examiner.id).all()
    return render_template("admin_examiners.html", examiners=examiners)

@app.route("/admin/examiners/new", methods=["GET", "POST"])
def new_examiner():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        phone = request.form["phone"].strip()
        department = request.form["department"].strip()
        if not name or not email or not password:
            flash("Name, email and password are required.", "danger")
            return redirect(url_for("new_examiner"))
        if User.query.filter_by(email=email).first():
            flash("That email is already registered.", "danger")
            return redirect(url_for("new_examiner"))
        user = User(email=email, name=name, phone=phone, department=department,
                    role="examiner", password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.add(Examiner(user=user, status="Approved"))
        db.session.commit()
        flash("Examiner added and approved.", "success")
        return redirect(url_for("admin_examiners"))
    return render_template("examiner_form.html")

@app.route("/admin/examiners/<int:examiner_id>/status", methods=["POST"])
def set_examiner_status(examiner_id):
    examiner = db.get_or_404(Examiner, examiner_id)
    status = request.form["status"]
    if status not in ("Approved", "Deactivated"):
        flash("Invalid status.", "danger")
    else:
        examiner.status = status
        db.session.commit()
        flash(f"{examiner.user.name} is now {status}.", "success")
    return redirect(url_for("admin_examiners"))

@app.route("/admin/students")
def admin_students():
    students = User.query.filter_by(role="student").order_by(User.id).all()
    return render_template("admin_students.html", students=students)

#Admin: assign examiners to examinations
@app.route("/admin/exams/<int:exam_id>/examiners", methods=["GET", "POST"])
def exam_examiners(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    assigned_ids = [a.examiner_id for a in exam.assignments]
    if request.method == "POST":
        try:
            user_id = int(request.form["examiner_id"])
        except ValueError:
            user_id = 0
        examiner = Examiner.query.filter_by(user_id=user_id, status="Approved").first()
        if examiner is None:
            flash("Please choose an approved examiner.", "danger")
        elif user_id in assigned_ids:
            flash("That examiner is already assigned to this examination.", "warning")
        else:
            db.session.add(ExamAssignment(exam_id=exam.id, examiner_id=user_id))
            db.session.commit()
            flash(f"{examiner.user.name} assigned to {exam.name}.", "success")
        return redirect(url_for("exam_examiners", exam_id=exam.id))
    approved = Examiner.query.filter_by(status="Approved").all()
    available = [e for e in approved if e.user_id not in assigned_ids]
    return render_template("exam_examiners.html", exam=exam, available=available)

@app.route("/admin/assignments/<int:assignment_id>/delete", methods=["POST"])
def delete_assignment(assignment_id):
    assignment = db.get_or_404(ExamAssignment, assignment_id)
    exam_id = assignment.exam_id
    has_slots = Slot.query.filter_by(exam_id=exam_id, examiner_id=assignment.examiner_id).first()
    if has_slots:
        flash("Cannot remove: this examiner already has slots for this examination.", "danger")
    else:
        db.session.delete(assignment)
        db.session.commit()
        flash("Examiner removed from this examination.", "success")
    return redirect(url_for("exam_examiners", exam_id=exam_id))

#Admin: examination phase

PHASES = {
    "open_slots": {"from": ["Draft", "Closed"], "to": "Slot Creation", "label": "Open slot cretaion"},
    "close_slots": {"from": ["Slot Creation"], "to": "Closed", "label": "Closed slot creation"},
    "open_booking": {"from": ["Closed"], "to": "Booking Open", "label": "Open Booking"},
    "close_booking": {"from": ["Booking Open"], "to": "Closed", "label": "Close booking"},
    "complete": {"from": ["Closed"], "to": "Completed", "label": "Mark Completed"},
}
@app.route("/admin/exams/<int:exam_id>/phase", methods=["POST"])
def change_phase(exam_id):
    exam = db.get_or_404(Examination, exam_id)
    action = request.form["action"]
    phase = PHASES.get(action)
    if phase is None:
        flash("Unknown action.", "danger")
    elif exam.status not in phase["from"]:
        flash(f"That is not possible while the examination is {exam.status}.", "danger")
    elif action == "open_slots" and not exam.assignments:
        flash("Assign atleast one examiner before opening slot creation.", "danger")
    elif action == "open_booking" and not exam.slots:
        flash("No slots exist yet, so booking cannot be opened.", "danger")
    else:
        exam.status = phase["to"]
        db.session.commit()
        flash(f"{exam.name} is now: {exam.status}.", "success")
    return redirect(url_for("admin_exams"))

if __name__ == "__main__":
    app.run(debug=True)