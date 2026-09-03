import os
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, abort
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


def get_subject_positions(student):
    positions = {}
    current_session = get_current_session()
    classmates_ids = [
        s.id for s in User.query.filter_by(role="student", assigned_class=student.assigned_class).all()
    ]
    result_filter = {"student_id": student.id}
    if current_session:
        result_filter["session_id"] = current_session.id
    subject_ids = {r.subject_id for r in AcademicResult.query.filter_by(**result_filter).all()}
    for subj_id in subject_ids:
        conditions = [
            AcademicResult.subject_id == subj_id,
            AcademicResult.student_id.in_(classmates_ids)
        ]
        if current_session:
            conditions.append(AcademicResult.session_id == current_session.id)
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


def get_class_position(student):
    current_session = get_current_session()
    classmates = User.query.filter_by(role="student", assigned_class=student.assigned_class).all()
    averages = []
    for s in classmates:
        s_filter = {"student_id": s.id}
        if current_session:
            s_filter["session_id"] = current_session.id
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
    for sub_id in selected_subject_ids:
        res = AcademicResult(
            student_id=current_user.id,
            subject_id=int(sub_id),
            session_id=current_session.id if current_session else None
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
            db.session.commit()
            flash("Online payment verified successfully! Your term clearance is now active.", "success")
        else:
            flash("Payment verification failed or was declined.", "danger")
    except Exception:
        flash("Verification service unavailable.", "danger")

    return redirect(url_for("student_dashboard"))


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


@app.route("/timetable")
@login_required
def view_timetable():
    if current_user.role == "student":
        class_name = current_user.assigned_class
    elif current_user.role == "teacher":
        class_name = current_user.assigned_class
    else:
        class_name = request.args.get("class_name", "")

    entries = TimetableEntry.query.filter_by(class_name=class_name).all() if class_name else []
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    return render_template("timetable.html", entries=entries, days=days, class_name=class_name)


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
                    session_id=current_session.id if current_session else None
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

            if not User.query.filter_by(username=username).first():
                new_user = User(
                    username=username,
                    full_name=full_name,
                    email=email,
                    role=role,
                    assigned_class=assigned_class,
                    parent_name=parent_name,
                    parent_email=parent_email,
                    parent_phone=parent_phone
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

        elif action == "set_current_session":
            session_id = request.form.get("session_id")
            Session.query.update({Session.is_current: False})
            selected = db.session.get(Session, int(session_id))
            if selected:
               selected.is_current = True
            db.session.commit()
            flash("Current session updated!", "success")

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
        results_published=published
    )
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


@app.route("/admin/toggle-results", methods=["POST"])
@login_required
def send_result_notifications():
    students = User.query.filter_by(role="student").all()
    sent_count = 0
    for student in students:
        if not student.parent_email:
            continue
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
    return sent_count


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
        sent = send_result_notifications()
        flash(f"Term results are now published and live for students! Notified {sent} parent(s) by email.", "info")
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
