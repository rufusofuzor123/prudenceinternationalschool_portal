import os
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, abort, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "prudence-secret-key-998877")

PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "sk_test_xxx_your_paystack_secret_key_xxx")

db_url = os.environ.get("DATABASE_URL", "sqlite:///prudence_portal.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_USERNAME")
mail = Mail(app)

UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
if os.path.exists(app.config["UPLOAD_FOLDER"]) and not os.path.isdir(app.config["UPLOAD_FOLDER"]):
    os.remove(app.config["UPLOAD_FOLDER"])
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


class SystemSetting(db.Model):
    __tablename__ = "system_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(50), nullable=False)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    assigned_class = db.Column(db.String(50), nullable=True)
    passport_pic = db.Column(db.String(200), default="default_passport.jpg")
    fee_paid = db.Column(db.Boolean, default=False)
    parent_name = db.Column(db.String(120), nullable=True)
    parent_email = db.Column(db.String(120), nullable=True)
    parent_phone = db.Column(db.String(20), nullable=True)
    qualification = db.Column(db.String(200), nullable=True)
    hire_date = db.Column(db.Date, nullable=True)
    staff_phone = db.Column(db.String(20), nullable=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class SchoolClass(db.Model):
    __tablename__ = "school_classes"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class Session(db.Model):
    __tablename__ = "sessions"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    is_current = db.Column(db.Boolean, default=False)


class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=True)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="Present")

    student = db.relationship("User", backref="attendance_records")
    session = db.relationship("Session", backref="attendance_records")


class TimetableEntry(db.Model):
    __tablename__ = "timetable_entries"
    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(50), nullable=False)
    day_of_week = db.Column(db.String(10), nullable=False)
    time_slot = db.Column(db.String(30), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    subject = db.relationship("Subject", backref="timetable_entries")
    teacher = db.relationship("User", backref="timetable_entries")


class FeeStructure(db.Model):
    __tablename__ = "fee_structures"
    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(50), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=True)
    term = db.Column(db.String(20), nullable=False, default="First Term")
    amount = db.Column(db.Float, nullable=False)

    session = db.relationship("Session", backref="fee_structures")


class Notice(db.Model):
    __tablename__ = "notices"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    body = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False)


class TeacherAssignment(db.Model):
    __tablename__ = "teacher_assignments"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    class_name = db.Column(db.String(50), nullable=False)

    teacher = db.relationship("User", backref="teaching_assignments")
    subject = db.relationship("Subject", backref="teaching_assignments")


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    reference = db.Column(db.String(100), nullable=False, unique=True)
    date_paid = db.Column(db.DateTime, nullable=False)

    student = db.relationship("User", backref="payments")
    session = db.relationship("Session", backref="payments")


class Event(db.Model):
    __tablename__ = "events"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    event_date = db.Column(db.Date, nullable=False)
    event_type = db.Column(db.String(30), nullable=False, default="General")


class Assignment(db.Model):
    __tablename__ = "assignments"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    class_name = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False)

    teacher = db.relationship("User", backref="assignments_created")
    subject = db.relationship("Subject", backref="assignments")


class Submission(db.Model):
    __tablename__ = "submissions"
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    answer_text = db.Column(db.Text, nullable=False)
    date_submitted = db.Column(db.DateTime, nullable=False)
    grade = db.Column(db.String(20), nullable=True)
    feedback = db.Column(db.Text, nullable=True)

    assignment = db.relationship("Assignment", backref="submissions")
    student = db.relationship("User", backref="submissions")


class Quiz(db.Model):
    __tablename__ = "quizzes"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    class_name = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=15)
    date_created = db.Column(db.DateTime, nullable=False)

    teacher = db.relationship("User", backref="quizzes_created")
    subject = db.relationship("Subject", backref="quizzes")


class Question(db.Model):
    __tablename__ = "questions"
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(300), nullable=False)
    option_b = db.Column(db.String(300), nullable=False)
    option_c = db.Column(db.String(300), nullable=False)
    option_d = db.Column(db.String(300), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)

    quiz = db.relationship("Quiz", backref="questions")


class QuizAttempt(db.Model):
    __tablename__ = "quiz_attempts"
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    score = db.Column(db.Float, nullable=False, default=0)
    total_questions = db.Column(db.Integer, nullable=False, default=0)
    date_taken = db.Column(db.DateTime, nullable=False)

    quiz = db.relationship("Quiz", backref="attempts")
    student = db.relationship("User", backref="quiz_attempts")


class AcademicResult(db.Model):
    __tablename__ = "academic_results"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=True)
    term = db.Column(db.String(20), nullable=False, default="First Term")
    ca1_score = db.Column(db.Float, default=0.0)
    ca2_score = db.Column(db.Float, default=0.0)
    exam_score = db.Column(db.Float, default=0.0)

    subject = db.relationship("Subject", backref="results")
    session = db.relationship("Session", backref="results")
    student = db.relationship("User", backref="academic_results")

    @property
    def total_score(self) -> float:
        return float(self.ca1_score + self.ca2_score + self.exam_score)

    @property
    def grade(self) -> str:
        score = self.total_score
        grade_letter = "F"
        if score >= 70.0:
            grade_letter = "A"
        elif score >= 60.0:
            grade_letter = "B"
        elif score >= 50.0:
            grade_letter = "C"
        elif score >= 40.0:
            grade_letter = "D"
        return grade_letter


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


def is_results_published() -> bool:
    setting = SystemSetting.query.filter_by(key="publish_results").first()
    return bool(setting and setting.value == "true")


def get_current_term() -> str:
    setting = SystemSetting.query.filter_by(key="current_term").first()
    return setting.value if setting else "First Term"


def redirect_role_dashboard(role: str):
    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    if role == "teacher":
        return redirect(url_for("teacher_dashboard"))
    return redirect(url_for("student_dashboard"))


@app.route("/", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect_role_dashboard(current_user.role)

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect_role_dashboard(user.role)
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password")
        new_pw = request.form.get("new_password")
        confirm_pw = request.form.get("confirm_password")

        if not current_user.check_password(current_pw):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("change_password"))

        if not new_pw or len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "danger")
            return redirect(url_for("change_password"))

        if new_pw != confirm_pw:
            flash("New password and confirmation do not match.", "danger")
            return redirect(url_for("change_password"))

        current_user.set_password(new_pw)
        db.session.commit()
        flash("Password changed successfully!", "success")
        return redirect_role_dashboard(current_user.role)

    return render_template("change_password.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username_or_email = request.form.get("username_or_email")
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        if user and user.email:
            from itsdangerous import URLSafeTimedSerializer
            serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
            token = serializer.dumps(user.id, salt="password-reset")
            reset_url = url_for("reset_password", token=token, _external=True)
            try:
                msg = Message(
                    subject="Password Reset - Prudence International School Portal",
                    recipients=[user.email],
                    body=f"Hello {user.full_name},\n\nClick the link below to reset your password. This link expires in 30 minutes.\n\n{reset_url}\n\nIf you did not request this, ignore this email."
                )
                mail.send(msg)
            except Exception:
                pass
        flash("If an account with that username/email exists, a reset link has been sent.", "info")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    try:
        user_id = serializer.loads(token, salt="password-reset", max_age=1800)
    except SignatureExpired:
        flash("This reset link has expired. Please request a new one.", "danger")
        return redirect(url_for("forgot_password"))
    except BadSignature:
        flash("Invalid reset link.", "danger")
        return redirect(url_for("forgot_password"))

    user = db.session.get(User, user_id)
    if not user:
        flash("Invalid reset link.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_pw = request.form.get("new_password")
        confirm_pw = request.form.get("confirm_password")
        if not new_pw or len(new_pw) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("reset_password", token=token))
        if new_pw != confirm_pw:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("reset_password", token=token))
        user.set_password(new_pw)
        db.session.commit()
        flash("Password reset successfully! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


def get_student_fee(student):
    current_session = get_current_session()
    query = FeeStructure.query.filter_by(class_name=student.assigned_class)
    if current_session:
        query = query.filter_by(session_id=current_session.id)
    fee = query.first()
    return fee.amount if fee else 50000.0


def get_current_session():
    return Session.query.filter_by(is_current=True).first()


def get_subject_positions(student, session_id=None):
    positions = {}
    if session_id is None:
        current_session = get_current_session()
        session_id = current_session.id if current_session else None
    classmates_ids = [
        s.id for s in User.query.filter_by(role="student", assigned_class=student.assigned_class).all()
    ]
    result_filter = {"student_id": student.id}
    if session_id:
        result_filter["session_id"] = session_id
    subject_ids = {r.subject_id for r in AcademicResult.query.filter_by(**result_filter).all()}
    for subj_id in subject_ids:
        conditions = [
            AcademicResult.subject_id == subj_id,
            AcademicResult.student_id.in_(classmates_ids)
        ]
        if session_id:
            conditions.append(AcademicResult.session_id == session_id)
        subj_results = AcademicResult.query.filter(*conditions).all()
        ranked = sorted(subj_results, key=lambda r: r.total_score, reverse=True)
        for idx, r in enumerate(ranked, start=1):
            if r.student_id == student.id:
                positions[subj_id] = (idx, len(ranked))
        subject_total = sum(r.total_score for r in subj_results)
        subject_avg = round(subject_total / len(subj_results), 2) if subj_results else 0
        positions.setdefault(subj_id, (None, len(ranked)))
        positions[subj_id] = positions[subj_id] + (subject_avg,)
    return positions


def get_class_position(student, session_id=None):
    if session_id is None:
        current_session = get_current_session()
        session_id = current_session.id if current_session else None
    classmates = User.query.filter_by(role="student", assigned_class=student.assigned_class).all()
    averages = []
    for s in classmates:
        s_filter = {"student_id": s.id}
        if session_id:
            s_filter["session_id"] = session_id
        s_results = AcademicResult.query.filter_by(**s_filter).all()
        avg = round(sum(r.total_score for r in s_results) / len(s_results), 2) if s_results else 0
        averages.append((s.id, avg))
    averages.sort(key=lambda x: x[1], reverse=True)
    for idx, (sid, avg) in enumerate(averages, start=1):
        if sid == student.id:
            return idx, len(averages), avg
    return None, len(averages), 0


@app.route("/student/dashboard", methods=["GET", "POST"])
@login_required
def student_dashboard():
    if current_user.role != "student":
        abort(403)

    available_subjects = Subject.query.all()
    current_session = get_current_session()
    result_filter = {"student_id": current_user.id}
    if current_session:
        result_filter["session_id"] = current_session.id
    results = AcademicResult.query.filter_by(**result_filter).all()
    published = is_results_published()

    if request.method == "POST" and "passport" in request.files:
        file = request.files["passport"]
        if file and allowed_file(file.filename):
            filename = secure_filename(f"user_{current_user.id}_{file.filename}")
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)
            current_user.passport_pic = filename
            db.session.commit()
            flash("Passport uploaded successfully!", "success")
            return redirect(url_for("student_dashboard"))

    subject_positions = get_subject_positions(current_user)
    class_pos, class_total, class_avg = get_class_position(current_user)

    attendance_filter = {"student_id": current_user.id}
    if current_session:
        attendance_filter["session_id"] = current_session.id
    attendance_records = Attendance.query.filter_by(**attendance_filter).order_by(Attendance.date.desc()).all()
    present_count = sum(1 for a in attendance_records if a.status == "Present")
    absent_count = sum(1 for a in attendance_records if a.status == "Absent")
    late_count = sum(1 for a in attendance_records if a.status == "Late")

    student_fee = get_student_fee(current_user)
    notices = Notice.query.order_by(Notice.date_posted.desc()).all()

    return render_template(
        "student_dashboard.html",
        notices=notices,
        subjects=available_subjects,
        results=results,
        results_published=published,
        subject_positions=subject_positions,
        class_position=class_pos,
        class_total=class_total,
        class_average=class_avg,
        attendance_records=attendance_records,
        present_count=present_count,
        absent_count=absent_count,
        late_count=late_count,
        student_fee=student_fee
    )


@app.route("/student/results-history")
@login_required
def results_history():
    if current_user.role != "student":
        abort(403)

    all_sessions = Session.query.all()
    selected_session_id = request.args.get("session_id", type=int)
    selected_term = request.args.get("term", "")

    results = []
    subject_positions = {}
    class_pos, class_total, class_avg = None, 0, 0

    if selected_session_id:
        result_filter = {"student_id": current_user.id, "session_id": selected_session_id}
        if selected_term:
            result_filter["term"] = selected_term
        results = AcademicResult.query.filter_by(**result_filter).all()
        subject_positions = get_subject_positions(current_user, session_id=selected_session_id)
        class_pos, class_total, class_avg = get_class_position(current_user, session_id=selected_session_id)

    return render_template(
        "results_history.html",
        all_sessions=all_sessions,
        selected_session_id=selected_session_id,
        selected_term=selected_term,
        results=results,
        subject_positions=subject_positions,
        class_position=class_pos,
        class_total=class_total,
        class_average=class_avg
    )


@app.route("/student/register-subjects", methods=["POST"])
@login_required
def register_subjects():
    if current_user.role != "student":
        abort(403)

    current_session = get_current_session()
    selected_subject_ids = request.form.getlist("subject_ids")
    delete_filter = {"student_id": current_user.id}
    if current_session:
        delete_filter["session_id"] = current_session.id
    AcademicResult.query.filter_by(**delete_filter).delete()
    current_term = get_current_term()
    for sub_id in selected_subject_ids:
        res = AcademicResult(
            student_id=current_user.id,
            subject_id=int(sub_id),
            session_id=current_session.id if current_session else None,
            term=current_term
        )
        db.session.add(res)

    db.session.commit()
    flash("Subjects registered successfully for the term!", "success")
    return redirect(url_for("student_dashboard"))


@app.route("/student/initialize-payment", methods=["POST"])
@login_required
def initialize_payment():
    if current_user.role != "student":
        abort(403)

    amount_in_naira = get_student_fee(current_user)
    amount_in_kobo = int(amount_in_naira * 100)
    student_email = current_user.email or f"{current_user.username}@prudence.edu.ng"

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "email": student_email,
        "amount": amount_in_kobo,
        "callback_url": url_for("verify_payment", _external=True),
        "metadata": {
            "student_id": current_user.id,
            "student_name": current_user.full_name
        }
    }

    try:
        response = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
        res_data = response.json()

        if res_data.get("status"):
            return redirect(res_data["data"]["authorization_url"])
        else:
            flash("Could not initialize online payment. Please try again.", "danger")
    except Exception:
        flash("Network error contacting payment gateway.", "danger")

    return redirect(url_for("student_dashboard"))


@app.route("/student/verify-payment")
@login_required
def verify_payment():
    reference = request.args.get("reference")
    if not reference:
        flash("No transaction reference provided.", "danger")
        return redirect(url_for("student_dashboard"))

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    }

    try:
        response = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
        res_data = response.json()

        if res_data.get("status") and res_data["data"]["status"] == "success":
            current_user.fee_paid = True
            from datetime import datetime
            current_session = get_current_session()
            paid_amount = res_data["data"]["amount"] / 100
            existing_payment = Payment.query.filter_by(reference=reference).first()
            if not existing_payment:
                db.session.add(Payment(
                    student_id=current_user.id,
                    session_id=current_session.id if current_session else None,
                    amount=paid_amount,
                    reference=reference,
                    date_paid=datetime.utcnow()
                ))
            db.session.commit()
            flash("Online payment verified successfully! Your term clearance is now active.", "success")
        else:
            flash("Payment verification failed or was declined.", "danger")
    except Exception:
        flash("Verification service unavailable.", "danger")

    return redirect(url_for("student_dashboard"))


@app.route("/receipts")
@login_required
def list_receipts():
    if current_user.role != "student":
        abort(403)
    payments = Payment.query.filter_by(student_id=current_user.id).order_by(Payment.date_paid.desc()).all()
    return render_template("receipts.html", payments=payments)


@app.route("/receipt/<int:payment_id>")
@login_required
def view_receipt(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        abort(404)
    if current_user.role == "student" and payment.student_id != current_user.id:
        abort(403)
    if current_user.role not in ["student", "admin"]:
        abort(403)
    return render_template("receipt.html", payment=payment)


@app.route("/teacher/dashboard")
@login_required
def teacher_dashboard():
    if current_user.role != "teacher":
        abort(403)

    class_students = User.query.filter_by(role="student", assigned_class=current_user.assigned_class).all()
    current_session = get_current_session()
    for s in class_students:
        result_filter = {"student_id": s.id}
        if current_session:
            result_filter["session_id"] = current_session.id
        s.filtered_results = AcademicResult.query.filter_by(**result_filter).all()
    notices = Notice.query.order_by(Notice.date_posted.desc()).all()
    my_assignments = TeacherAssignment.query.filter_by(teacher_id=current_user.id).all()
    return render_template("teacher_dashboard.html", students=class_students, notices=notices, my_assignments=my_assignments)


@app.route("/teacher/grade/<int:student_id>", methods=["POST"])
@login_required
def enter_grades(student_id: int):
    if current_user.role != "teacher":
        abort(403)

    current_session = get_current_session()
    grade_filter = {"student_id": student_id}
    if current_session:
        grade_filter["session_id"] = current_session.id
    results = AcademicResult.query.filter_by(**grade_filter).all()
    for res in results:
        ca1 = request.form.get(f"ca1_{res.id}", 0)
        ca2 = request.form.get(f"ca2_{res.id}", 0)
        exam = request.form.get(f"exam_{res.id}", 0)
        res.ca1_score = float(ca1)
        res.ca2_score = float(ca2)
        res.exam_score = float(exam)

    db.session.commit()
    flash("Student grades updated successfully!", "success")
    return redirect(url_for("teacher_dashboard"))


@app.route("/student/quizzes")
@login_required
def student_quizzes():
    if current_user.role != "student":
        abort(403)
    quizzes = Quiz.query.filter_by(class_name=current_user.assigned_class).all()
    my_attempts = {a.quiz_id: a for a in QuizAttempt.query.filter_by(student_id=current_user.id).all()}
    return render_template("student_quizzes.html", quizzes=quizzes, my_attempts=my_attempts)


@app.route("/student/quiz/<int:quiz_id>/take", methods=["GET", "POST"])
@login_required
def take_quiz(quiz_id):
    if current_user.role != "student":
        abort(403)
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz or quiz.class_name != current_user.assigned_class:
        abort(403)

    existing = QuizAttempt.query.filter_by(quiz_id=quiz_id, student_id=current_user.id).first()
    if existing:
        flash("You have already taken this quiz.", "danger")
        return redirect(url_for("student_quizzes"))

    questions = Question.query.filter_by(quiz_id=quiz_id).all()

    if request.method == "POST":
        correct_count = 0
        for q in questions:
            selected = request.form.get(f"q_{q.id}")
            if selected == q.correct_option:
                correct_count += 1
        score = round((correct_count / len(questions)) * 100, 1) if questions else 0
        from datetime import datetime as dt
        db.session.add(QuizAttempt(
            quiz_id=quiz_id,
            student_id=current_user.id,
            score=score,
            total_questions=len(questions),
            date_taken=dt.utcnow()
        ))
        db.session.commit()
        flash(f"Quiz submitted! Your score: {score}%", "success")
        return redirect(url_for("student_quizzes"))

    return render_template("take_quiz.html", quiz=quiz, questions=questions)


@app.route("/teacher/quizzes", methods=["GET", "POST"])
@login_required
def teacher_quizzes():
    if current_user.role != "teacher":
        abort(403)

    my_teaching = TeacherAssignment.query.filter_by(teacher_id=current_user.id).all()

    if request.method == "POST":
        subject_id = request.form.get("quiz_subject_id")
        class_name = request.form.get("quiz_class_name")
        title = request.form.get("quiz_title")
        duration = request.form.get("quiz_duration", 15)
        if subject_id and class_name and title:
            from datetime import datetime as dt
            db.session.add(Quiz(
                teacher_id=current_user.id,
                subject_id=int(subject_id),
                class_name=class_name,
                title=title,
                duration_minutes=int(duration),
                date_created=dt.utcnow()
            ))
            db.session.commit()
            flash("Quiz created! Now add questions to it.", "success")
        return redirect(url_for("teacher_quizzes"))

    my_quizzes = Quiz.query.filter_by(teacher_id=current_user.id).order_by(Quiz.date_created.desc()).all()
    return render_template("teacher_quizzes.html", my_teaching=my_teaching, my_quizzes=my_quizzes)


@app.route("/teacher/quiz/<int:quiz_id>", methods=["GET", "POST"])
@login_required
def manage_quiz(quiz_id):
    if current_user.role != "teacher":
        abort(403)
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz or quiz.teacher_id != current_user.id:
        abort(403)

    if request.method == "POST":
        q_text = request.form.get("question_text")
        opt_a = request.form.get("option_a")
        opt_b = request.form.get("option_b")
        opt_c = request.form.get("option_c")
        opt_d = request.form.get("option_d")
        correct = request.form.get("correct_option")
        if q_text and opt_a and opt_b and opt_c and opt_d and correct:
            db.session.add(Question(
                quiz_id=quiz_id,
                question_text=q_text,
                option_a=opt_a,
                option_b=opt_b,
                option_c=opt_c,
                option_d=opt_d,
                correct_option=correct
            ))
            db.session.commit()
            flash("Question added!", "success")
        return redirect(url_for("manage_quiz", quiz_id=quiz_id))

    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    attempts = QuizAttempt.query.filter_by(quiz_id=quiz_id).all()
    return render_template("manage_quiz.html", quiz=quiz, questions=questions, attempts=attempts)


@app.route("/student/assignments")
@login_required
def student_assignments():
    if current_user.role != "student":
        abort(403)
    assignments = Assignment.query.filter_by(class_name=current_user.assigned_class).order_by(Assignment.due_date.asc()).all()
    my_submissions = {s.assignment_id: s for s in Submission.query.filter_by(student_id=current_user.id).all()}
    return render_template("student_assignments.html", assignments=assignments, my_submissions=my_submissions)


@app.route("/student/assignment/<int:assignment_id>/submit", methods=["POST"])
@login_required
def submit_assignment(assignment_id):
    if current_user.role != "student":
        abort(403)
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment or assignment.class_name != current_user.assigned_class:
        abort(403)

    existing = Submission.query.filter_by(assignment_id=assignment_id, student_id=current_user.id).first()
    answer_text = request.form.get("answer_text")
    from datetime import datetime as dt
    if existing:
        existing.answer_text = answer_text
        existing.date_submitted = dt.utcnow()
    else:
        db.session.add(Submission(
            assignment_id=assignment_id,
            student_id=current_user.id,
            answer_text=answer_text,
            date_submitted=dt.utcnow()
        ))
    db.session.commit()
    flash("Assignment submitted!", "success")
    return redirect(url_for("student_assignments"))


@app.route("/teacher/assignments", methods=["GET", "POST"])
@login_required
def teacher_assignments():
    if current_user.role != "teacher":
        abort(403)

    my_teaching = TeacherAssignment.query.filter_by(teacher_id=current_user.id).all()

    if request.method == "POST":
        subject_id = request.form.get("assign_subject_id")
        class_name = request.form.get("assign_class_name")
        title = request.form.get("assign_title")
        description = request.form.get("assign_description")
        due_date_str = request.form.get("assign_due_date")
        if subject_id and class_name and title and due_date_str:
            from datetime import datetime as dt
            due_date = dt.strptime(due_date_str, "%Y-%m-%d").date()
            db.session.add(Assignment(
                teacher_id=current_user.id,
                subject_id=int(subject_id),
                class_name=class_name,
                title=title,
                description=description,
                due_date=due_date,
                date_posted=dt.utcnow()
            ))
            db.session.commit()
            flash("Assignment posted!", "success")
        return redirect(url_for("teacher_assignments"))

    my_assignments = Assignment.query.filter_by(teacher_id=current_user.id).order_by(Assignment.due_date.desc()).all()
    return render_template("teacher_assignments.html", my_teaching=my_teaching, my_assignments=my_assignments)


@app.route("/teacher/assignment/<int:assignment_id>/submissions")
@login_required
def view_submissions(assignment_id):
    if current_user.role != "teacher":
        abort(403)
    assignment = db.session.get(Assignment, assignment_id)
    if not assignment or assignment.teacher_id != current_user.id:
        abort(403)
    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()
    return render_template("view_submissions.html", assignment=assignment, submissions=submissions)


@app.route("/teacher/submission/<int:submission_id>/grade", methods=["POST"])
@login_required
def grade_submission(submission_id):
    if current_user.role != "teacher":
        abort(403)
    submission = db.session.get(Submission, submission_id)
    if not submission or submission.assignment.teacher_id != current_user.id:
        abort(403)
    submission.grade = request.form.get("grade")
    submission.feedback = request.form.get("feedback")
    db.session.commit()
    flash("Feedback saved!", "success")
    return redirect(url_for("view_submissions", assignment_id=submission.assignment_id))


@app.route("/calendar")
@login_required
def view_calendar():
    events = Event.query.order_by(Event.event_date.asc()).all()
    return render_template("calendar.html", events=events)


@app.route("/timetable")
@login_required
def view_timetable():
    if current_user.role == "student":
        class_name = current_user.assigned_class
        classes = None
    else:
        classes = SchoolClass.query.all()
        default_class = current_user.assigned_class if current_user.role == "teacher" else ""
        class_name = request.args.get("class_name", default_class or "")

    entries = TimetableEntry.query.filter_by(class_name=class_name).all() if class_name else []
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    return render_template("timetable.html", entries=entries, days=days, class_name=class_name, classes=classes)


@app.route("/teacher/attendance", methods=["GET", "POST"])
@login_required
def mark_attendance():
    if current_user.role != "teacher":
        abort(403)
    if not current_user.assigned_class:
        abort(403)

    from datetime import date as date_cls
    current_session = get_current_session()
    class_students = User.query.filter_by(role="student", assigned_class=current_user.assigned_class).all()

    if request.method == "POST":
        selected_date = request.form.get("date")
        for student in class_students:
            status = request.form.get(f"status_{student.id}", "Present")
            existing = Attendance.query.filter_by(
                student_id=student.id,
                date=selected_date,
                session_id=current_session.id if current_session else None
            ).first()
            if existing:
                existing.status = status
            else:
                db.session.add(Attendance(
                    student_id=student.id,
                    date=selected_date,
                    status=status,
                    session_id=current_session.id if current_session else None
                ))
        db.session.commit()
        flash("Attendance saved successfully!", "success")
        return redirect(url_for("mark_attendance"))

    today = date_cls.today().isoformat()
    return render_template("mark_attendance.html", students=class_students, today=today)


@app.route("/teacher/grade-class/<int:assignment_id>", methods=["GET", "POST"])
@login_required
def grade_class(assignment_id):
    if current_user.role != "teacher":
        abort(403)

    assignment = db.session.get(TeacherAssignment, assignment_id)
    if not assignment or assignment.teacher_id != current_user.id:
        abort(403)

    current_session = get_current_session()
    class_students = User.query.filter_by(role="student", assigned_class=assignment.class_name).all()

    if request.method == "POST":
        for student in class_students:
            result_filter = {
                "student_id": student.id,
                "subject_id": assignment.subject_id,
            }
            if current_session:
                result_filter["session_id"] = current_session.id
            res = AcademicResult.query.filter_by(**result_filter).first()
            ca1 = request.form.get(f"ca1_{student.id}")
            ca2 = request.form.get(f"ca2_{student.id}")
            exam = request.form.get(f"exam_{student.id}")
            if ca1 is None:
                continue
            if not res:
                res = AcademicResult(
                    student_id=student.id,
                    subject_id=assignment.subject_id,
                    session_id=current_session.id if current_session else None,
                    term=get_current_term()
                )
                db.session.add(res)
            res.ca1_score = float(ca1 or 0)
            res.ca2_score = float(ca2 or 0)
            res.exam_score = float(exam or 0)
        db.session.commit()
        flash("Scores saved!", "success")
        return redirect(url_for("grade_class", assignment_id=assignment_id))

    student_results = []
    for student in class_students:
        result_filter = {"student_id": student.id, "subject_id": assignment.subject_id}
        if current_session:
            result_filter["session_id"] = current_session.id
        res = AcademicResult.query.filter_by(**result_filter).first()
        student_results.append((student, res))

    return render_template("grade_class.html", assignment=assignment, student_results=student_results)


@app.route("/admin/export/users")
@login_required
def export_users():
    if current_user.role != "admin":
        abort(403)
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Full Name", "Username", "Role", "Email", "Class", "Fee Paid", "Parent Name", "Parent Email", "Parent Phone"])
    for u in User.query.all():
        writer.writerow([u.id, u.full_name, u.username, u.role, u.email or "", u.assigned_class or "", u.fee_paid, u.parent_name or "", u.parent_email or "", u.parent_phone or ""])
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=users.csv"
    return response


@app.route("/admin/export/results")
@login_required
def export_results():
    if current_user.role != "admin":
        abort(403)
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student", "Class", "Subject", "CA1", "CA2", "Exam", "Total", "Grade", "Session"])
    for r in AcademicResult.query.all():
        writer.writerow([
            r.student.full_name if r.student else "",
            r.student.assigned_class if r.student else "",
            r.subject.name if r.subject else "",
            r.ca1_score, r.ca2_score, r.exam_score, r.total_score, r.grade,
            r.session.name if r.session else ""
        ])
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=results.csv"
    return response


@app.route("/admin/export/attendance")
@login_required
def export_attendance():
    if current_user.role != "admin":
        abort(403)
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student", "Class", "Date", "Status", "Session"])
    for a in Attendance.query.all():
        writer.writerow([
            a.student.full_name if a.student else "",
            a.student.assigned_class if a.student else "",
            a.date, a.status,
            a.session.name if a.session else ""
        ])
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=attendance.csv"
    return response


@app.route("/admin/export/payments")
@login_required
def export_payments():
    if current_user.role != "admin":
        abort(403)
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student", "Class", "Reference", "Amount", "Date Paid", "Session"])
    for p in Payment.query.all():
        writer.writerow([
            p.student.full_name if p.student else "",
            p.student.assigned_class if p.student else "",
            p.reference, p.amount, p.date_paid,
            p.session.name if p.session else ""
        ])
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=payments.csv"
    return response


@app.route("/admin/dashboard", methods=["GET", "POST"])
@login_required
def admin_dashboard():
    if current_user.role != "admin":
        abort(403)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "create_user":
            username = request.form.get("username")
            password = request.form.get("password")
            full_name = request.form.get("full_name")
            email = request.form.get("email")
            role = request.form.get("role")
            assigned_class = request.form.get("assigned_class")
            parent_name = request.form.get("parent_name")
            parent_email = request.form.get("parent_email")
            parent_phone = request.form.get("parent_phone")
            qualification = request.form.get("qualification")
            hire_date_str = request.form.get("hire_date")
            staff_phone = request.form.get("staff_phone")
            from datetime import datetime as dt
            hire_date = dt.strptime(hire_date_str, "%Y-%m-%d").date() if hire_date_str else None

            if not User.query.filter_by(username=username).first():
                new_user = User(
                    username=username,
                    full_name=full_name,
                    email=email,
                    role=role,
                    assigned_class=assigned_class,
                    parent_name=parent_name,
                    parent_email=parent_email,
                    parent_phone=parent_phone,
                    qualification=qualification,
                    hire_date=hire_date,
                    staff_phone=staff_phone
                )
                new_user.set_password(password)
                db.session.add(new_user)
                db.session.commit()
                flash(f"New {role} account created successfully!", "success")
            else:
                flash("Username already exists.", "danger")

        elif action == "create_subject":
            sub_name = request.form.get("subject_name")
            if sub_name and not Subject.query.filter_by(name=sub_name).first():
                db.session.add(Subject(name=sub_name))
                db.session.commit()
                flash("Subject added to portal system!", "success")

        elif action == "create_class":
            class_name = request.form.get("class_name")
            if class_name and not SchoolClass.query.filter_by(name=class_name).first():
                db.session.add(SchoolClass(name=class_name))
                db.session.commit()
                flash("Class added successfully!", "success")

        elif action == "create_session":
            session_name = request.form.get("session_name")
            if session_name and not Session.query.filter_by(name=session_name).first():
                db.session.add(Session(name=session_name))
                db.session.commit()
                flash("Session added successfully!", "success")

        elif action == "set_current_term":
            new_term = request.form.get("current_term")
            if new_term:
                setting = SystemSetting.query.filter_by(key="current_term").first()
                if not setting:
                    setting = SystemSetting(key="current_term", value=new_term)
                    db.session.add(setting)
                else:
                    setting.value = new_term
                db.session.commit()
                flash(f"Current term set to {new_term}!", "success")

        elif action == "set_current_session":
            session_id = request.form.get("session_id")
            Session.query.update({Session.is_current: False})
            selected = db.session.get(Session, int(session_id))
            if selected:
               selected.is_current = True
            db.session.commit()
            flash("Current session updated!", "success")

        elif action == "promote_students":
            from_class = request.form.get("promote_from")
            to_class = request.form.get("promote_to")
            if from_class and to_class and from_class != to_class:
                students_to_promote = User.query.filter_by(role="student", assigned_class=from_class).all()
                count = len(students_to_promote)
                for s in students_to_promote:
                    s.assigned_class = to_class
                    s.fee_paid = False
                db.session.commit()
                flash(f"Promoted {count} student(s) from {from_class} to {to_class}. Fee status reset for the new class.", "success")
            else:
                flash("Please select two different classes.", "danger")

        elif action == "assign_teacher":
            ta_teacher_id = request.form.get("ta_teacher_id")
            ta_subject_id = request.form.get("ta_subject_id")
            ta_class_name = request.form.get("ta_class_name")
            if ta_teacher_id and ta_subject_id and ta_class_name:
                existing = TeacherAssignment.query.filter_by(
                    teacher_id=int(ta_teacher_id),
                    subject_id=int(ta_subject_id),
                    class_name=ta_class_name
                ).first()
                if not existing:
                    db.session.add(TeacherAssignment(
                        teacher_id=int(ta_teacher_id),
                        subject_id=int(ta_subject_id),
                        class_name=ta_class_name
                    ))
                    db.session.commit()
                    flash("Teacher assigned to class/subject!", "success")
                else:
                    flash("This assignment already exists.", "danger")

        elif action == "add_event":
            event_title = request.form.get("event_title")
            event_desc = request.form.get("event_description")
            event_date_str = request.form.get("event_date")
            event_type = request.form.get("event_type", "General")
            if event_title and event_date_str:
                from datetime import datetime as dt
                event_date = dt.strptime(event_date_str, "%Y-%m-%d").date()
                db.session.add(Event(title=event_title, description=event_desc, event_date=event_date, event_type=event_type))
                db.session.commit()
                flash("Event added to calendar!", "success")

        elif action == "post_notice":
            notice_title = request.form.get("notice_title")
            notice_body = request.form.get("notice_body")
            if notice_title and notice_body:
                from datetime import datetime
                db.session.add(Notice(title=notice_title, body=notice_body, date_posted=datetime.utcnow()))
                db.session.commit()
                flash("Notice posted!", "success")

        elif action == "add_fee_structure":
            fs_class_name = request.form.get("fs_class_name")
            fs_amount = request.form.get("fs_amount")
            fs_term = request.form.get("fs_term", "First Term")
            current_session = get_current_session()
            if fs_class_name and fs_amount:
                existing = FeeStructure.query.filter_by(
                    class_name=fs_class_name,
                    term=fs_term,
                    session_id=current_session.id if current_session else None
                ).first()
                if existing:
                    existing.amount = float(fs_amount)
                else:
                    db.session.add(FeeStructure(
                        class_name=fs_class_name,
                        term=fs_term,
                        amount=float(fs_amount),
                        session_id=current_session.id if current_session else None
                    ))
                db.session.commit()
                flash("Fee structure saved!", "success")

        elif action == "add_timetable_entry":
            class_name = request.form.get("tt_class_name")
            day_of_week = request.form.get("tt_day")
            time_slot = request.form.get("tt_time")
            subject_id = request.form.get("tt_subject_id")
            teacher_id = request.form.get("tt_teacher_id") or None
            if class_name and day_of_week and time_slot and subject_id:
                db.session.add(TimetableEntry(
                    class_name=class_name,
                    day_of_week=day_of_week,
                    time_slot=time_slot,
                    subject_id=int(subject_id),
                    teacher_id=int(teacher_id) if teacher_id else None
                ))
                db.session.commit()
                flash("Timetable entry added!", "success")


    users = User.query.all()
    subjects = Subject.query.all()
    classes = SchoolClass.query.all()
    sessions = Session.query.all()
    teachers = User.query.filter_by(role="teacher").all()
    timetable_entries = TimetableEntry.query.all()
    fee_structures = FeeStructure.query.all()
    notices = Notice.query.order_by(Notice.date_posted.desc()).all()
    teacher_assignments = TeacherAssignment.query.all()
    published = is_results_published()
    current_term = get_current_term()

    import json
    all_students = User.query.filter_by(role="student").all()
    paid_count = sum(1 for s in all_students if s.fee_paid)
    unpaid_count = len(all_students) - paid_count

    class_names = [c.name for c in classes]
    avg_scores = []
    attendance_rates = []
    current_session = get_current_session()
    for cname in class_names:
        class_students = [s for s in all_students if s.assigned_class == cname]
        student_ids = [s.id for s in class_students]

        result_filter = [AcademicResult.student_id.in_(student_ids)] if student_ids else [AcademicResult.student_id == -1]
        if current_session:
            result_filter.append(AcademicResult.session_id == current_session.id)
        class_results = AcademicResult.query.filter(*result_filter).all()
        avg = round(sum(r.total_score for r in class_results) / len(class_results), 1) if class_results else 0
        avg_scores.append(avg)

        att_filter = [Attendance.student_id.in_(student_ids)] if student_ids else [Attendance.student_id == -1]
        if current_session:
            att_filter.append(Attendance.session_id == current_session.id)
        class_attendance = Attendance.query.filter(*att_filter).all()
        present = sum(1 for a in class_attendance if a.status == "Present")
        rate = round((present / len(class_attendance)) * 100, 1) if class_attendance else 0
        attendance_rates.append(rate)

    chart_data = json.dumps({
        "fee_labels": ["Paid", "Unpaid"],
        "fee_values": [paid_count, unpaid_count],
        "class_labels": class_names,
        "avg_scores": avg_scores,
        "attendance_rates": attendance_rates
    })

    return render_template(
        "admin_dashboard.html",
        users=users,
        subjects=subjects,
        classes=classes,
        sessions=sessions,
        teachers=teachers,
        timetable_entries=timetable_entries,
        fee_structures=fee_structures,
        notices=notices,
        teacher_assignments=teacher_assignments,
        results_published=published,
        current_term=current_term,
        chart_data=chart_data
    )
@app.route("/admin/staff-records")
@login_required
def staff_records():
    if current_user.role != "admin":
        abort(403)
    teachers = User.query.filter_by(role="teacher").all()
    return render_template("staff_records.html", teachers=teachers)


@app.route("/admin/delete-user/<int:user_id>", methods=["POST"])
@login_required
def delete_user(user_id):
    if current_user.role != "admin":
        abort(403)
    user_to_delete = db.session.get(User, user_id)
    if not user_to_delete:
        flash("User not found.", "danger")
        return redirect(url_for("admin_dashboard"))
    if user_to_delete.username == "admin":
        flash("Cannot delete the default admin account.", "danger")
        return redirect(url_for("admin_dashboard"))
    if user_to_delete.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f"User {user_to_delete.full_name} deleted.", "success")
    except Exception:
        db.session.rollback()
        flash(f"Could not delete {user_to_delete.full_name} — they have existing records (results, attendance, payments, etc.) linked to their account. Remove or reassign those first, or contact support for a full purge.", "danger")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reset-portal-data", methods=["POST"])
@login_required
def reset_portal_data():
    if current_user.role != "admin":
        abort(403)

    confirm_text = request.form.get("confirm_text")
    if confirm_text != "RESET":
        flash("You must type RESET exactly to confirm data wipe.", "danger")
        return redirect(url_for("admin_dashboard"))

    from sqlalchemy import text
    db.session.execute(text("DROP SCHEMA public CASCADE"))
    db.session.execute(text("CREATE SCHEMA public"))
    db.session.commit()
    db.create_all()

    default_admin = User(
        username="admin",
        full_name="School Administrator",
        email="admin@prudence.edu.ng",
        role="admin"
    )
    default_admin.set_password("AdminPass123!")
    db.session.add(default_admin)
    db.session.add(SystemSetting(key="publish_results", value="false"))
    db.session.commit()

    flash("Portal data has been reset. Log in fresh with the default admin account.", "success")
    return redirect(url_for("login"))


@app.route("/admin/delete-assignment/<int:assignment_id>", methods=["POST"])
@login_required
def delete_assignment(assignment_id):
    if current_user.role != "admin":
        abort(403)
    a = db.session.get(TeacherAssignment, assignment_id)
    if a:
        db.session.delete(a)
        db.session.commit()
        flash("Assignment removed.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete-event/<int:event_id>", methods=["POST"])
@login_required
def delete_event(event_id):
    if current_user.role != "admin":
        abort(403)
    e = db.session.get(Event, event_id)
    if e:
        db.session.delete(e)
        db.session.commit()
        flash("Event removed.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete-notice/<int:notice_id>", methods=["POST"])
@login_required
def delete_notice(notice_id):
    if current_user.role != "admin":
        abort(403)
    notice = db.session.get(Notice, notice_id)
    if notice:
        db.session.delete(notice)
        db.session.commit()
        flash("Notice deleted.", "success")
    return redirect(url_for("admin_dashboard"))


def send_sms(phone_number, message):
    api_key = os.environ.get("TERMII_API_KEY")
    sender_id = os.environ.get("TERMII_SENDER_ID")
    if not api_key or not sender_id or not phone_number:
        return False
    try:
        response = requests.post(
            "https://api.ng.termii.com/api/sms/send",
            json={
                "to": phone_number,
                "from": sender_id,
                "sms": message,
                "type": "plain",
                "channel": "generic",
                "api_key": api_key
            },
            timeout=10
        )
        return response.status_code == 200
    except Exception:
        return False


def send_result_notifications():
    students = User.query.filter_by(role="student").all()
    sent_count = 0
    sms_sent_count = 0
    for student in students:
        if student.parent_email:
            try:
                msg = Message(
                    subject="Term Result Published - Prudence International School",
                    recipients=[student.parent_email],
                    body=(
                        f"Dear {student.parent_name or 'Parent/Guardian'},\n\n"
                        f"The term result for {student.full_name} has been published and is now "
                        f"available on the school portal.\n\n"
                        f"Please log in to the portal to view or print the result sheet.\n\n"
                        f"Regards,\nPrudence International School"
                    )
                )
                mail.send(msg)
                sent_count += 1
            except Exception:
                pass

        if student.parent_phone:
            sms_text = (
                f"Dear {student.parent_name or 'Parent/Guardian'}, the term result for "
                f"{student.full_name} has been published. Please log in to the school portal to view it. "
                f"- Prudence International School"
            )
            if send_sms(student.parent_phone, sms_text):
                sms_sent_count += 1

    return sent_count, sms_sent_count


@app.route("/admin/toggle-results", methods=["POST"])
@login_required
def toggle_results():
    if current_user.role != "admin":
        abort(403)

    setting = SystemSetting.query.filter_by(key="publish_results").first()
    if not setting:
        setting = SystemSetting(key="publish_results", value="false")
        db.session.add(setting)

    setting.value = "false" if setting.value == "true" else "true"
    db.session.commit()

    if setting.value == "true":
        import threading
        app_ctx = app.app_context()
        def notify_in_background():
            with app_ctx:
                send_result_notifications()
        threading.Thread(target=notify_in_background, daemon=True).start()
        flash("Term results are now published and live for students! Parent notifications (email/SMS) are being sent in the background.", "info")
    else:
        flash("Term results are now hidden/unpublished.", "info")
    return redirect(url_for("admin_dashboard"))


with app.app_context():
    db.create_all()

    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    existing_columns = [col["name"] for col in inspector.get_columns("academic_results")]
    if "session_id" not in existing_columns:
        db.session.execute(text("ALTER TABLE academic_results ADD COLUMN session_id INTEGER REFERENCES sessions(id)"))
        db.session.commit()

    user_columns = [col["name"] for col in inspector.get_columns("users")]
    if "parent_name" not in user_columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN parent_name VARCHAR(120)"))
        db.session.commit()
    if "parent_email" not in user_columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN parent_email VARCHAR(120)"))
        db.session.commit()
    if "parent_phone" not in user_columns:
        db.session.execute(text("ALTER TABLE users ADD COLUMN parent_phone VARCHAR(20)"))
        db.session.commit()

    if "payments" not in inspector.get_table_names():
        Payment.__table__.create(db.engine)

    user_columns_2 = [col["name"] for col in inspector.get_columns("users")]
    if "qualification" not in user_columns_2:
        db.session.execute(text("ALTER TABLE users ADD COLUMN qualification VARCHAR(200)"))
        db.session.commit()
    if "hire_date" not in user_columns_2:
        db.session.execute(text("ALTER TABLE users ADD COLUMN hire_date DATE"))
        db.session.commit()
    if "staff_phone" not in user_columns_2:
        db.session.execute(text("ALTER TABLE users ADD COLUMN staff_phone VARCHAR(20)"))
        db.session.commit()

    if "events" not in inspector.get_table_names():
        Event.__table__.create(db.engine)

    if "assignments" not in inspector.get_table_names():
        Assignment.__table__.create(db.engine)
    if "submissions" not in inspector.get_table_names():
        Submission.__table__.create(db.engine)

    if "quizzes" not in inspector.get_table_names():
        Quiz.__table__.create(db.engine)
    if "questions" not in inspector.get_table_names():
        Question.__table__.create(db.engine)
    if "quiz_attempts" not in inspector.get_table_names():
        QuizAttempt.__table__.create(db.engine)

    if not User.query.filter_by(username="admin").first():
        default_admin = User(
            username="admin",
            full_name="School Administrator",
            email="admin@prudence.edu.ng",
            role="admin"
        )
        default_admin.set_password("AdminPass123!")
        db.session.add(default_admin)

    if not SystemSetting.query.filter_by(key="publish_results").first():
        db.session.add(SystemSetting(key="publish_results", value="false"))

    db.session.commit()

if __name__ == "__main__":
    app.run(debug=True)
