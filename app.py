import os 
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Examiner, Course, Examination, Slot, Booking

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
    """Every URL under /admin, /examiner or /student needs the matching role."""
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

# ---------------- Admin: dashboard -----------
@app.route("/admin")
def admin_dashboard():
    stats = [
        ("Courses", Course.query.count()),
        ("Examinations", Examination.query.count()),
        ("Examiners", User.query.filter_by(role="examiner").count()),
        ("Students", User.query.filter_by(role="student").count()),
        ("Exam slots", Slot.query.count()),
        ("Bookings", Booking.query.count()),
    ]
    return render_template("admin_dashboard.html", stats=stats)

# ---------------- Admin: courses ----------------
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
        flash("Cannot delete: this course still has examinations. Set it to Inactive instead.", "danger")
    else:
        db.session.delete(course)
        db.session.commit()
        flash("Course deleted.", "success")
    return redirect(url_for("admin_courses"))

if __name__ == "__main__":
    app.run(debug=True)