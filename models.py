from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    department = db.Column(db.String(100))
    role = db.Column(db.String(20), nullable=False)

class Examiner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    status = db.Column(db.String(20), default="Pending")
     # Pending / Approved / Deactivated
    user = db.relationship("User", backref=db.backref("profile", uselist=False))


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="Active")

class Examination(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    name = db.Column(db.String(100),nullable=False)
    exam_type = db.Column(db.String(30), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    max_marks = db.Column(db.Integer, nullable=False)
    slot_start = db.Column(db.Date)
    slot_end = db.Column(db.Date)
    booking_start = db.Column(db.Date)
    booking_end = db.Column(db.Date)
    status = db.Column(db.String(20), default="Draft")
    course = db.relationship("Course", backref="examinations")

class ExamAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("exam_id", "examiner_id"),) # same examiner can't be assigned twice
    # same examiner can't be assigned twice
    exam = db.relationship("Examination", backref="assignments")
    examiner = db.relationship("User", backref="assignments")

    #ExamAssignment table holds one row per examiner per exam

class Rubric(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False)
    criterion = db.Column(db.String(100), nullable=False)
    max_marks = db.Column(db.Integer, nullable=False)
    weightage = db.Column(db.Float)
    description = db.Column(db.Text)
    exam = db.relationship("Examination", backref="rubrics")

class Slot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False)
    examiner_id =db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    available = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="Available")
    exam = db.relationship("Examination", backref="slots")
    examiner = db.relationship("User", backref="slots")

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey("slot.id"), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey("examination.id"), nullable=False)
    booked_at = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default="Booked")
    remarks = db.Column(db.Text)
    published = db.Column(db.Boolean, default=False)
    student = db.relationship("User", backref="bookings")
    slot = db.relationship("Slot", backref="bookings")
    exam = db.relationship("Examination")

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey("rubric.id"), nullable=False)
    marks = db.Column(db.Integer, nullable=False)
    booking = db.relationship("Booking", backref="scores")
    rubric = db.relationship("Rubric")