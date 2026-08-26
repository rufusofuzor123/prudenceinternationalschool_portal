éclass AcademicResult(db.model):
class SchoolClass(db.Model):
    __tablename__ = "school_classes"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class Session(db.Model):
    __tablename__ = "sessions"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    is_current = db.Column(db.Boolean, default=False)
import os
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "prudence-secret-key-998877")

PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "sk_test_xxx_your_paystack_secret_key_xxx")

db_url = os.environ.get("DATABASE_URL", "sqlite:///prudence_portal.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class AcademicResult(db.Model):
    __tablename__ = "academic_results"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    term = db.Column(db.String(20), nullable=False, default="First Term")
    ca1_score = db.Column(db.Float, default=0.0)
    ca2_score = db.Column(db.Float, default=0.0)
    exam_score = db.Column(db.Float, default=0.0)

    subject = db.relationship("Subject", backref="results")

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


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/student/dashboard", methods=["GET", "POST"])
@login_required
def student_dashboard():
    if current_user.role != "student":
        abort(403)

    available_subjects = Subject.query.all()
    results = AcademicResult.query.filter_by(student_id=current_user.id).all()
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

    return render_template(
        "student_dashboard.html",
        subjects=available_subjects,
        results=results,
        results_published=published
    )


@app.route("/student/register-subjects", methods=["POST"])
@login_required
def register_subjects():
    if current_user.role != "student":
        abort(403)

    selected_subject_ids = request.form.getlist("subject_ids")
    AcademicResult.query.filter_by(student_id=current_user.id).delete()
    for sub_id in selected_subject_ids:
        res = AcademicResult(student_id=current_user.id, subject_id=int(sub_id))
        db.session.add(res)

    db.session.commit()
    flash("Subjects registered successfully for the term!", "success")
    return redirect(url_for("student_dashboard"))


@app.route("/student/initialize-payment", methods=["POST"])
@login_required
def initialize_payment():
    if current_user.role != "student":
        abort(403)

    amount_in_naira = float(request.form.get("amount", 50000))
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
    return render_template("teacher_dashboard.html", students=class_students)


@app.route("/teacher/grade/<int:student_id>", methods=["POST"])
@login_required
def enter_grades(student_id: int):
    if current_user.role != "teacher":
        abort(403)

    results = AcademicResult.query.filter_by(student_id=student_id).all()
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

            if not User.query.filter_by(username=username).first():
                new_user = User(
                    username=username,
                    full_name=full_name,
                    email=email,
                    role=role,
                    assigned_class=assigned_class
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
            flas("Current session updated!", "success")


users = User.query.all()
    subjects = Subject.query.all()
    classes = SchoolClass.query.all()
    sessions = Session.query.all()
    published = is_results_published()
    return render_template(
        "admin_dashboard.html",
        users=users,
        subjects=subjects,
        classes=classes,
        sessions=sessions,
        results_published=published
    )
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

    status_msg = "published and live for students!" if setting.value == "true" else "hidden/unpublished."
    flash(f"Term results are now {status_msg}", "info")
    return redirect(url_for("admin_dashboard"))


with app.app_context():
    db.create_all()
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
