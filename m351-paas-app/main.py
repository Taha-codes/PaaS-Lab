"""Student Manager: a small CRUD app for the App Engine + Firestore lab (Part II).

Everything the platform needs to know lives in app.yaml. This file only
contains application logic: list, add, edit and delete students, plus a
button that restores the sample data.
"""

import logging
import os
import re
import threading

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

from seed_data import SEED_STUDENTS

# --- Settings (set in app.yaml under env_variables) -------------------------

APP_TITLE = os.environ.get("APP_TITLE", "Student Manager")
APP_COLOR = os.environ.get("APP_COLOR", "#2563eb")
COLLECTION = os.environ.get("STUDENTS_COLLECTION", "students")

# App Engine sets these automatically. Locally they fall back to "local".
GAE_VERSION = os.environ.get("GAE_VERSION", "local")
GAE_INSTANCE = os.environ.get("GAE_INSTANCE", "local")

FIELDS = ("student_id", "name", "major", "year", "email")
MAJORS = (
    "Computer Science",
    "Artificial Intelligence",
    "Software Engineering",
    "Data Science",
    "Cybersecurity",
    "Business Administration",
)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("student-manager")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-for-anything-real")


# --- Firestore ----------------------------------------------------------------

_db = None


def get_db():
    """Create the Firestore client on first use.

    On App Engine the client finds the project and credentials by itself:
    no host, port, username or password is configured anywhere.
    """
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def students_ref():
    return get_db().collection(COLLECTION)


def write_seed_data():
    """Write the sample students. Fixed document IDs make this safe to repeat."""
    batch = get_db().batch()
    for i, student in enumerate(SEED_STUDENTS, start=1):
        batch.set(students_ref().document(f"seed-{i:02d}"), student)
    batch.commit()


def delete_all_students():
    """Delete every document in the collection, in batches of up to 400."""
    deleted = 0
    while True:
        docs = list(students_ref().limit(400).stream())
        if not docs:
            return deleted
        batch = get_db().batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()
        deleted += len(docs)


# --- Seed on first run --------------------------------------------------------
# The first instance that ever runs creates a marker document and loads the
# sample data. create() fails if the marker already exists, so two instances
# starting at the same moment cannot both seed, and data a student deletes is
# never quietly brought back by a later instance.

_seed_checked = False
_seed_lock = threading.Lock()


def seed_on_first_run():
    global _seed_checked
    if _seed_checked:
        return
    with _seed_lock:
        if _seed_checked:
            return
        marker = get_db().collection("_lab_meta").document("seed")
        try:
            marker.create({"seeded_at": firestore.SERVER_TIMESTAMP, "by_version": GAE_VERSION})
        except AlreadyExists:
            log.info("SEED skipped: database was already seeded")
        else:
            write_seed_data()
            log.info("SEED loaded %d sample students into '%s'", len(SEED_STUDENTS), COLLECTION)
        _seed_checked = True


@app.before_request
def ensure_seeded():
    if request.endpoint != "static":
        seed_on_first_run()


# --- Helpers ------------------------------------------------------------------

def read_form():
    """Return (data, errors) from the submitted student form."""
    data = {field: request.form.get(field, "").strip() for field in FIELDS}
    errors = {}
    if not data["student_id"]:
        errors["student_id"] = "Enter a student ID, for example S1013."
    if not data["name"]:
        errors["name"] = "Enter the student's full name."
    if data["major"] not in MAJORS:
        errors["major"] = "Choose a major from the list."
    if data["year"] not in {"1", "2", "3", "4", "5"}:
        errors["year"] = "Choose a year from 1 to 5."
    if not EMAIL_RE.match(data["email"]):
        errors["email"] = "Enter an email address like name@example.edu."
    if not errors:
        data["year"] = int(data["year"])
    return data, errors


def text_color_for(hex_color):
    """Pick dark or white text so the header stays readable with any APP_COLOR."""
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return "#ffffff"

    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    return "#16202b" if luminance > 0.4 else "#ffffff"


@app.context_processor
def inject_platform_info():
    return {
        "app_title": APP_TITLE,
        "app_color": APP_COLOR,
        "app_text_color": text_color_for(APP_COLOR),
        "gae_version": GAE_VERSION,
        "gae_instance": GAE_INSTANCE,
        "majors": MAJORS,
    }


# --- Routes -------------------------------------------------------------------

@app.get("/")
def index():
    """READ: list every student, sorted by name."""
    docs = students_ref().order_by("name").stream()
    students = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    log.info("READ %d students", len(students))
    return render_template("index.html", students=students)


@app.route("/students/new", methods=["GET", "POST"])
def add_student():
    """CREATE: add a new student document with an auto-generated ID."""
    if request.method == "POST":
        data, errors = read_form()
        if errors:
            return render_template("form.html", mode="add", student=data, errors=errors), 400
        _, doc_ref = students_ref().add(data)
        log.info("CREATE student %s (%s) as document %s", data["student_id"], data["name"], doc_ref.id)
        flash(f"Added {data['name']}.")
        return redirect(url_for("index"))
    return render_template("form.html", mode="add", student={}, errors={})


@app.route("/students/<doc_id>/edit", methods=["GET", "POST"])
def edit_student(doc_id):
    """UPDATE: change the fields of an existing student document."""
    doc_ref = students_ref().document(doc_id)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        abort(404)
    if request.method == "POST":
        data, errors = read_form()
        if errors:
            return render_template("form.html", mode="edit", student={"id": doc_id, **data}, errors=errors), 400
        doc_ref.update(data)
        log.info("UPDATE student %s (%s), document %s", data["student_id"], data["name"], doc_id)
        flash(f"Saved changes to {data['name']}.")
        return redirect(url_for("index"))
    return render_template("form.html", mode="edit", student={"id": doc_id, **snapshot.to_dict()}, errors={})


@app.post("/students/<doc_id>/delete")
def delete_student(doc_id):
    """DELETE: remove one student document."""
    doc_ref = students_ref().document(doc_id)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        abort(404)
    name = snapshot.to_dict().get("name", doc_id)
    doc_ref.delete()
    log.info("DELETE student %s, document %s", name, doc_id)
    flash(f"Deleted {name}.")
    return redirect(url_for("index"))


@app.post("/reset")
def reset_data():
    """Delete every student and load the sample data again."""
    removed = delete_all_students()
    write_seed_data()
    log.info("RESET removed %d students, loaded %d sample students", removed, len(SEED_STUDENTS))
    flash(f"Reset the demo data: {len(SEED_STUDENTS)} sample students are back.")
    return redirect(url_for("index"))


@app.errorhandler(404)
def not_found(_error):
    return render_template("not_found.html"), 404


if __name__ == "__main__":
    # Local run only. On App Engine, gunicorn starts the app (see app.yaml).
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8080)), debug=True)
