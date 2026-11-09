import os 
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Examiner

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

def check_role(role):
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

@app.route("/admin")
@login_required
def admin_dashboard():
    check_role("admin")
    return render_template("admin_dashboard.html")

@app.route("/examiner")
@login_required
def examiner_dashboard():
    check_role("examiner")
    return render_template("examiner_dashboard.html")

@app.route("/student")
@login_required
def student_dashboard():
    check_role("student")
    return render_template("student_dashboard.html")

@app.route("/forgot")
def forgot():
    return "Contact the Admin to reset your password."

if __name__ == "__main__":
    app.run(debug=True)