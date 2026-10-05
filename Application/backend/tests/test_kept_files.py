"""Kept syllabi: the original file, in a private bucket (Phase 1 D24).

Three properties carry it:

* **A file is only ever reached through its row.** The object is named after
  the `syllabus_parses` row, read as the user; nothing in a request names an
  object. Someone else's parse id finds nothing.
* **No file outlives its record.** The row is committed before the upload, and
  an account is purged only once storage confirms every file is gone -- or it
  waits for the next purge.
* **A storage failure never costs a parse.** The extraction is what the app
  runs on; the file is provenance.
"""
import base64
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import app.main
from app._database.db import get_db
from app._database.models import CourseModel, SyllabusParseModel, UserModel, utc_now
from app.Auth.dependencies import get_current_user
from app.Intake.schemas.syllabus import ApplyAssessment, ApplyRequest, SyllabusUpload
from app.Intake.services import storage
from app.Intake.services.kept_files import discard_files, kept_files, read_kept_file
from app.Intake.services.syllabus_service import apply, parse
from app.Users.schemas.user import DELETION_GRACE_DAYS
from app.Users.services.user_service import delete_user, purge_expired_users
from app.api.routes.intake import download_name
from conftest import make_course, make_user

PDF = b"%PDF-1.4 my syllabus"


def upload(content=PDF, media_type="application/pdf", filename="cpsc221.pdf"):
    return SyllabusUpload(filename=filename, media_type=media_type,
                          content_base64=base64.b64encode(content).decode())


@pytest.fixture
def termed(db, user):
    user.current_school_year, user.current_semester, user.first_year_calendar_year = 2, "Fall", 2025
    db.commit()
    return user


def confirmed():
    return ApplyRequest(course_code="CPSC 221", course_name="Algorithms", assessments=[
        ApplyAssessment(name="Assignments", category="Assignment", weight=30, count=3),
        ApplyAssessment(name="Midterm", category="Midterm", weight=30),
        ApplyAssessment(name="Final exam", category="Final", weight=40, date_tba=True),
    ])


def past_the_deadline():
    return (utc_now() + timedelta(days=DELETION_GRACE_DAYS + 1)).date()


# --- the storage client ----------------------------------------------------

def test_put_get_delete(_no_storage_network):
    storage.put("syllabi/x", PDF, "application/pdf")
    assert storage.get("syllabi/x") == PDF
    assert _no_storage_network.objects["syllabi/x"] == (PDF, "application/pdf")
    storage.delete("syllabi/x")
    assert "syllabi/x" not in _no_storage_network.objects


def test_put_never_overwrites(_no_storage_network):
    storage.put("syllabi/x", PDF, "application/pdf")
    with pytest.raises(storage.StorageError, match="412"):
        storage.put("syllabi/x", b"someone else's", "application/pdf")
    assert storage.get("syllabi/x") == PDF


def test_deleting_what_is_not_there_is_done(_no_storage_network):
    storage.delete("syllabi/never")  # no error


def test_a_refusal_is_an_error(_no_storage_network):
    _no_storage_network.fail = 403
    for call in (lambda: storage.put("a", PDF, "application/pdf"), lambda: storage.get("a"),
                 lambda: storage.delete("a")):
        with pytest.raises(storage.StorageError, match="403"):
            call()


def test_no_bucket_means_not_configured(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "SYLLABUS_BUCKET", None)
    assert not storage.configured()
    with pytest.raises(storage.NotConfigured):
        storage.get("syllabi/x")


def test_the_request_shapes(monkeypatch):
    """Names are one path segment (slashes encoded), and the upload carries
    the no-overwrite precondition."""
    seen = []

    class Ok:
        status_code, content = 200, b""

    monkeypatch.setattr(storage, "_request", lambda method, url, **kw: seen.append((method, url, kw)) or Ok())
    storage.put("syllabi/a b", PDF, "text/plain")
    storage.get("syllabi/a b")
    storage.delete("syllabi/a b")
    (m1, u1, k1), (m2, u2, k2), (m3, u3, _) = seen
    assert (m1, u1) == ("POST", "https://storage.googleapis.com/upload/storage/v1/b/suite-bucket/o")
    assert k1["params"] == {"uploadType": "media", "name": "syllabi/a b", "ifGenerationMatch": "0"}
    assert k1["headers"] == {"Content-Type": "text/plain"} and k1["data"] == PDF
    assert (m2, u2, k2["params"]) == (
        "GET", "https://storage.googleapis.com/storage/v1/b/suite-bucket/o/syllabi%2Fa%20b", {"alt": "media"})
    assert (m3, u3) == ("DELETE", "https://storage.googleapis.com/storage/v1/b/suite-bucket/o/syllabi%2Fa%20b")


# --- keeping the file on a parse -------------------------------------------

def test_a_parse_keeps_the_file_named_after_its_row(db, termed, _no_storage_network):
    result = parse(db, termed.id, upload())
    row = db.query(SyllabusParseModel).filter(SyllabusParseModel.id == result.id).one()
    assert (row.file_kept, row.media_type) == (True, "application/pdf")
    assert _no_storage_network.objects[f"syllabi/{row.id}"] == (PDF, "application/pdf")


def test_the_name_carries_nothing_about_the_person(db, termed, _no_storage_network):
    parse(db, termed.id, upload())
    [name] = _no_storage_network.objects
    assert str(termed.id) not in name and termed.email not in name


def test_without_a_bucket_the_parse_stands_and_nothing_is_kept(db, termed, monkeypatch, _no_storage_network):
    from app.config import settings
    monkeypatch.setattr(settings, "SYLLABUS_BUCKET", None)
    result = parse(db, termed.id, upload())
    assert result.extract.course_code == "CPSC 221"
    assert db.query(SyllabusParseModel).one().file_kept is False
    assert _no_storage_network.calls == []


def test_a_failed_upload_costs_the_parse_nothing(db, termed, _no_storage_network):
    _no_storage_network.fail = 503
    result = parse(db, termed.id, upload())
    assert result.extract.course_code == "CPSC 221"
    assert db.query(SyllabusParseModel).one().file_kept is False


# --- finding and serving it ------------------------------------------------

def test_a_kept_file_is_listed_behind_its_course_and_served(db, termed):
    parsed = parse(db, termed.id, upload())
    built = apply(db, termed.id, parsed.id, confirmed())
    [kept] = kept_files(db, termed.id, built.course_id)
    assert kept.id == parsed.id
    row, content = read_kept_file(db, termed.id, parsed.id)
    assert (row.filename, content) == ("cpsc221.pdf", PDF)


def test_someone_else_finds_nothing(db, termed):
    parsed = parse(db, termed.id, upload())
    built = apply(db, termed.id, parsed.id, confirmed())
    other = make_user(db, "other@example.com")
    assert read_kept_file(db, other.id, parsed.id) is None
    assert kept_files(db, other.id, built.course_id) == []


def test_a_file_that_was_not_kept_is_not_served(db, termed, _no_storage_network):
    _no_storage_network.fail = 503
    parsed = parse(db, termed.id, upload())
    _no_storage_network.fail = None
    assert read_kept_file(db, termed.id, parsed.id) is None


def test_deleting_the_course_keeps_the_file_with_the_parse(db, termed, _no_storage_network):
    from app.Grades.services.course_service import delete_course
    parsed = parse(db, termed.id, upload())
    built = apply(db, termed.id, parsed.id, confirmed())
    delete_course(db, termed.id, built.course_id)
    assert read_kept_file(db, termed.id, parsed.id)[1] == PDF


@pytest.mark.parametrize("given, expected", [
    ("cpsc221.pdf", "cpsc221.pdf"),
    ('evil".pdf\r\nSet-Cookie: x', "evil_.pdf__Set-Cookie_ x"),
    ("", "syllabus"),
    (None, "syllabus"),
    ("é.pdf", "_.pdf"),
])
def test_the_download_name_cannot_break_the_header(given, expected):
    assert download_name(given) == expected


@pytest.fixture
def client(db, termed):
    app.main.app.dependency_overrides[get_current_user] = lambda: termed
    app.main.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app.main.app)
    finally:
        app.main.app.dependency_overrides.clear()


def test_the_routes(db, termed, client, _no_storage_network):
    parsed = parse(db, termed.id, upload())
    built = apply(db, termed.id, parsed.id, confirmed())
    base = f"/api/intake/{termed.id}"
    listed = client.get(f"{base}/courses/{built.course_id}/syllabi").json()
    assert [(k["id"], k["filename"], k["media_type"]) for k in listed] == [
        (str(parsed.id), "cpsc221.pdf", "application/pdf")]

    got = client.get(f"{base}/syllabus/{parsed.id}/file")
    assert got.status_code == 200 and got.content == PDF
    assert got.headers["content-type"] == "application/pdf"
    assert got.headers["content-disposition"] == 'attachment; filename="cpsc221.pdf"'
    assert got.headers["x-content-type-options"] == "nosniff"

    assert client.get(f"{base}/syllabus/{built.course_id}/file").status_code == 404
    _no_storage_network.fail = 500
    assert client.get(f"{base}/syllabus/{parsed.id}/file").status_code == 502


# --- deleting the account --------------------------------------------------

def test_purging_an_account_deletes_its_files_first(db, termed, _no_storage_network):
    parse(db, termed.id, upload())
    other = make_user(db, "other@example.com")
    other.current_school_year, other.current_semester, other.first_year_calendar_year = 2, "Fall", 2025
    db.commit()
    theirs = parse(db, other.id, upload(b"%PDF-1.4 theirs"))
    delete_user(db, termed.id)

    assert purge_expired_users(db, on_day=past_the_deadline()) == 1
    assert list(_no_storage_network.objects) == [f"syllabi/{theirs.id}"]
    assert db.query(UserModel).filter(UserModel.id == termed.id).first() is None


def test_if_storage_cannot_confirm_the_account_waits(db, termed, _no_storage_network):
    parsed = parse(db, termed.id, upload())
    delete_user(db, termed.id)
    _no_storage_network.fail = 503

    assert purge_expired_users(db, on_day=past_the_deadline()) == 0
    assert db.query(UserModel).filter(UserModel.id == termed.id).first() is not None
    assert db.query(SyllabusParseModel).filter(SyllabusParseModel.id == parsed.id).first() is not None

    _no_storage_network.fail = None
    assert purge_expired_users(db, on_day=past_the_deadline()) == 1
    assert _no_storage_network.objects == {}


def test_an_upload_the_row_never_recorded_is_deleted_too(db, termed, _no_storage_network):
    """The upload landed, the commit marking it kept did not: the object is
    still named after the row, so the purge still finds it."""
    parsed = parse(db, termed.id, upload())
    row = db.query(SyllabusParseModel).filter(SyllabusParseModel.id == parsed.id).one()
    row.file_kept = False
    db.commit()
    assert discard_files(db, termed.id) == 1
    assert _no_storage_network.objects == {}


def test_without_a_bucket_kept_files_hold_the_purge(db, termed, monkeypatch):
    from app.config import settings
    parse(db, termed.id, upload())
    monkeypatch.setattr(settings, "SYLLABUS_BUCKET", None)
    with pytest.raises(storage.NotConfigured):
        discard_files(db, termed.id)


def test_without_a_bucket_or_a_kept_file_there_is_nothing_to_do(db, termed, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "SYLLABUS_BUCKET", None)
    parse(db, termed.id, upload())
    assert discard_files(db, termed.id) == 0
    make_course(db, termed.id, "X 100")
    delete_user(db, termed.id)
    assert purge_expired_users(db, on_day=past_the_deadline()) == 1
    assert db.query(CourseModel).count() == 0
