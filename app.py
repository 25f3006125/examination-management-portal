import os
from datetime import date, time
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
        ("Exam slots", Slot.query.count(), url_for("admin_slots")),
        ("Bookings", Booking.query.count(), url_for("admin_bookings")),
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

#Admin: slots, bookings and search
@app.route("/admin/slots")
def admin_slots():
    slots = Slot.query.order_by(Slot.date, Slot.start_time).all()
    return render_template("admin_slots.html", slots=slots)

@app.route("/admin/bookings")
def admin_bookings():
    bookings = Booking.query.order_by(Booking.id.desc()).all()
    return render_template("admin_bookings.html", bookings=bookings)

@app.route("/admin/search")
def admin_search():
    q = request.args.get("q", "").strip()
    results = {"students": [], "examiners": [], "exams": [], "bookings": []}
    if q:
        like = f"%{q}%"
        q_id = int(q) if q.isdigit() and len(q) < 10 else -1
        results["students"] = User.query.filter(
            User.role == "student",
            db.or_(User.name.ilike(like), User.email.ilike(like), User.id == q_id)).all()
        results["examiners"] = Examiner.query.join(User).filter(
            db.or_(User.name.ilike(like), User.email.ilike(like), Examiner.id == q_id)).all()
        results["exams"] = Examination.query.join(Course).filter(
            db.or_(Examination.name.ilike(like), Course.code.ilike(like), Examination.id == q_id)).all()
        results["bookings"] = (Booking.query.join(User, Booking.student_id == User.id).join(Examination, Booking.exam_id == Examination.id)
            .filter(db.or_(User.name.ilike(like), Examination.name.ilike(like), Booking.id == q_id)).all())
    return render_template("admin_search.html", q=q, results=results)

@app.route("/admin/bookings/<int:booking_id>/reschedule", methods=["GET", "POST"])
def reschedule_booking(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.status != "Booked" or booking.exam.status == "Completed":
        flash("Only active bookings of examinations that are not completed can be rescheduled.", "danger")
        return redirect(url_for("admin_bookings"))
    old_slot = booking.slot
    if request.method == "POST":
        try:
            new_id = int(request.form["slot_id"])
        except ValueError:
            new_id = 0
        new_slot = db.session.get(Slot, new_id)
        if (new_slot is None or new_slot.exam_id != booking.exam_id or new_slot.id == old_slot.id
                or new_slot.status != "Available" or new_slot.available < 1):
            flash("Please choose another slot of the same examination that still has a free seat.", "danger")
            return redirect(url_for("reschedule_booking", booking_id=booking.id))
        new_slot.available -= 1
        if new_slot.available == 0:
            new_slot.status = "Full"
        old_slot.available += 1
        if old_slot.status == "Full":
            old_slot.status = "Available"
        booking.slot = new_slot
        db.session.commit()
        flash("Booking moved to the new slot.", "success")
        return redirect(url_for("admin_bookings"))
    slots = Slot.query.filter(Slot.exam_id == booking.exam_id, Slot.id != old_slot.id, Slot.status == "Available", 
                              Slot.available > 0).order_by(Slot.date, Slot.start_time).all()
    return render_template("reschedule_form.html", booking=booking, slots=slots)

@app.route("/admin/assignments/<int:assignment_id>/replace", methods=["POST"])
def replace_examiner(assignment_id):
    assignment = db.get_or_404(ExamAssignment, assignment_id)
    exam_id = assignment.exam_id
    old_id = assignment.examiner_id
    try:
        new_id = int(request.form["examiner_id"])
    except ValueError:
        new_id = 0
    new_examiner = Examiner.query.filter_by(user_id=new_id, status="Approved").first()
    already = ExamAssignment.query.filter_by(exam_id=exam_id, examiner_id=new_id).first()
    if new_examiner is None:
        flash("Please choose an approved examiner.", "danger")
    elif already:
        flash("That examiner is already assigned to this examination.", "warning")
    else:
        slots = Slot.query.filter_by(exam_id=exam_id, examiner_id=old_id).all()
        for slot in slots:
            slot.examiner_id = new_id
        assignment.examiner_id = new_id
        db.session.commit()
        flash(f"Examiner replaced by {new_examiner.user.name}. {len(slots)} slot(s) moved to the new examiner.", "success")
    return redirect(url_for("exam_examiners", exam_id=exam_id))

def get_my_exam(exam_id):
    assignment = ExamAssignment.query.filter_by(exam_id=exam_id, examiner_id=current_user.id).first()
    if assignment is None:
        abort(403)
    return assignment.exam
def get_my_slot(slot_id):
    slot = db.get_or_404(Slot, slot_id)
    if slot.examiner_id != current_user.id:
        abort(403)
    return slot
def slot_window_problem(exam):
    today = date.today()
    if exam.status != "Slot Creation":
        return "Slot creation is not open for this examination."
    if today < exam.slot_start or today > exam.slot_end:
        return f"Slots can only be managed between {exam.slot_start} and {exam.slot_end}."
    return None
def slot_change_problem(slot):
    problem = slot_window_problem(slot.exam)
    if problem:
        return problem
    if Booking.query.filter_by(slot_id=slot.id).first():
        return "This slot has bookings, so it cannot be changed or removed."
    return None
def read_slot_form(slot=None):
    try:
        slot_date = date.fromisoformat(request.form["date"])
        start = time.fromisoformat(request.form["start_time"])
        end = time.fromisoformat(request.form["end_time"])
        capacity = int(request.form["capacity"])
    except ValueError:
        return None, "Please fill in the date, both times and the capacity correctly."
    if slot_date < date.today():
        return None, "The slot date cannot be in the past."
    if end <= start:
        return None, "The end time must be after the start time."
    if capacity < 1:
        return None, "Capacity must be at least 1."
    for other in Slot.query.filter_by(examiner_id=current_user.id, date=slot_date).all():
        if slot is not None and other.id == slot.id:
            continue
        if start < other.end_time and end > other.start_time:
            return None, f"This overlaps with another of your slots ({other.start_time.strftime('%H:%M')} - {other.end_time.strftime('%H:%M')})."
    return {"date": slot_date, "start_time": start, "end_time": end, "capacity": capacity}, None
@app.route("/examiner")
def examiner_dashboard():
    me = current_user.id
    my_bookings = Booking.query.join(Slot).filter(Slot.examiner_id == me)
    stats = [
        ("Assigned examinations", ExamAssignment.query.filter_by(examiner_id=me).count(), url_for("examiner_exams")),
        ("Slots created", Slot.query.filter_by(examiner_id=me).count(), url_for("examiner_slots")),
        ("Students booked", my_bookings.filter(Booking.status != "Cancelled").count(), url_for("examiner_students")),
        ("Pending evaluations", my_bookings.filter(Booking.status == "Booked").count(), url_for("examiner_students", show="pending")),
    ]
    return render_template("examiner_dashboard.html", stats=stats)
@app.route("/examiner/exams")
def examiner_exams():
    assignments = ExamAssignment.query.filter_by(examiner_id=current_user.id).order_by(ExamAssignment.id).all()
    exams = [a.exam for a in assignments]
    open_now = {e.id: slot_window_problem(e) is None for e in exams}
    return render_template("examiner_exams.html", exams=exams, open_now=open_now)
@app.route("/examiner/exams/<int:exam_id>/slots", methods=["GET", "POST"])
def examiner_exam_slots(exam_id):
    exam = get_my_exam(exam_id)
    problem = slot_window_problem(exam)
    if request.method == "POST":
        if problem:
            flash(problem, "danger")
        else:
            values, error = read_slot_form()
            if error:
                flash(error, "danger")
            else:
                db.session.add(Slot(exam_id=exam.id, examiner_id=current_user.id,available=values["capacity"], **values))
                db.session.commit()
                flash("Slot added.", "success")
        return redirect(url_for("examiner_exam_slots", exam_id=exam.id))
    slots = Slot.query.filter_by(exam_id=exam.id, examiner_id=current_user.id).order_by(Slot.date, Slot.start_time).all()
    return render_template("examiner_exam_slots.html", exam=exam, slots=slots, problem=problem, today=date.today())
@app.route("/examiner/slots")
def examiner_slots():
    slots = Slot.query.filter_by(examiner_id=current_user.id).order_by(Slot.date, Slot.start_time).all()
    return render_template("examiner_slots.html", slots=slots)
@app.route("/examiner/slots/<int:slot_id>/edit", methods=["GET", "POST"])
def edit_slot(slot_id):
    slot = get_my_slot(slot_id)
    problem = slot_change_problem(slot)
    if problem:
        flash(problem, "danger")
        return redirect(url_for("examiner_exam_slots", exam_id=slot.exam_id))
    if request.method == "POST":
        values, error = read_slot_form(slot)
        if error:
            flash(error, "danger")
            return redirect(url_for("edit_slot", slot_id=slot.id))
        slot.date = values["date"]
        slot.start_time = values["start_time"]
        slot.end_time = values["end_time"]
        slot.capacity = values["capacity"]
        slot.available = values["capacity"]
        db.session.commit()
        flash("Slot updated.", "success")
        return redirect(url_for("examiner_exam_slots", exam_id=slot.exam_id))
    return render_template("slot_form.html", slot=slot, today=date.today())
@app.route("/examiner/slots/<int:slot_id>/delete", methods=["POST"])
def delete_slot(slot_id):
    slot = get_my_slot(slot_id)
    exam_id = slot.exam_id
    problem = slot_change_problem(slot)
    if problem:
        flash(problem, "danger")
    else:
        db.session.delete(slot)
        db.session.commit()
        flash("Slot removed.", "success")
    return redirect(url_for("examiner_exam_slots", exam_id=exam_id))
@app.route("/examiner/students")
def examiner_students():
    show = request.args.get("show", "all")
    query = (Booking.query.join(Slot)
             .filter(Slot.examiner_id == current_user.id, Booking.status != "Cancelled"))
    if show == "pending":
        query = query.filter(Booking.status == "Booked")
    bookings = query.order_by(Slot.date, Slot.start_time).all()
    return render_template("examiner_students.html", bookings=bookings, show=show)
@app.route("/examiner/bookings/<int:booking_id>/evaluate", methods=["GET", "POST"])
def evaluate_booking(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.slot.examiner_id != current_user.id:
        abort(403)
    if booking.status == "Cancelled":
        flash("This booking was cancelled, so it cannot be evaluated.", "danger")
        return redirect(url_for("examiner_students"))
    rubrics = booking.exam.rubrics
    if not rubrics:
        flash("This examination has no rubric criteria yet. Ask the Admin to add them.", "danger")
        return redirect(url_for("examiner_students"))
    if request.method == "POST":
        marks = {}
        for rubric in rubrics:
            try:
                value = int(request.form[f"marks_{rubric.id}"])
            except (ValueError, KeyError):
                value = -1
            if value < 0 or value > rubric.max_marks:
                flash(f"Marks for {rubric.criterion} must be a whole number from 0 to {rubric.max_marks}.", "danger")
                return redirect(url_for("evaluate_booking", booking_id=booking.id))
            marks[rubric.id] = value
        for rubric in rubrics:
            score = Score.query.filter_by(booking_id=booking.id, rubric_id=rubric.id).first()
            if score is None:
                score = Score(booking_id=booking.id, rubric_id=rubric.id, marks=0)
                db.session.add(score)
            score.marks = marks[rubric.id]
        booking.remarks = request.form.get("remarks", "").strip()
        booking.published = "publish" in request.form
        booking.status = "Completed"
        db.session.commit()
        flash("Evaluation saved.", "success")
        return redirect(url_for("examiner_students"))
    saved = {s.rubric_id: s.marks for s in booking.scores}
    return render_template("evaluate_form.html", booking=booking, rubrics=rubrics, saved=saved)

@app.route("/examiner/profile", methods=["GET", "POST"])
def examiner_profile():
    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for("examiner_profile"))
        current_user.name = name
        current_user.phone = request.form["phone"].strip()
        current_user.department = request.form["department"].strip()
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("examiner_profile"))
    return render_template("examiner_profile.html")

if __name__ == "__main__":
    app.run(debug=True)