"""One input, anywhere: read a line, decide which module it belongs to, file it.

The tokenizer already says what is in the text. All this adds is the routing
rule and the lookups that need a database -- which account "savings" means, which
course "cs221" is, which category "groceries" is.

The routing rule is deliberately small and ordered, because a wrong guess here
is worse than no omnibox at all:

1. A score out of a maximum can only be a grade. Nothing else is written "78/100".
2. An amount can only be money. A bare integer never counts as one, so this
   fires on "$5" and "4.50" and not on "COSC 121".
3. Everything else is a task, which is the only kind that needs nothing but words.

Filing goes through each module's own service, so an omnibox expense is
indistinguishable from one typed into the money dialog -- same signing, same
validation, same everything.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app._database.models import AccountModel, SpendCategoryModel
from app.Finances.schemas.transaction import TransactionCreate, TransactionKind
from app.Finances.services.transaction_service import create_transaction
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.grade_service import add_grade
from app.Grades.utils.enums import GradeCategory
from app.Omnibox.schemas.omnibox import OmniboxKind, OmniboxPreview, OmniboxResult
from app.Tasks.schemas.task import MAX_ESTIMATED_MINUTES, TaskCreate
from app.Grades.services.course_lookup import resolve_course
from app.Tasks.services.task_service import create_task, user_exists
from app.shared.tokenizer import Parsed, parse

#: A word in the title that names the category, so "cosc121 midterm 78/100"
#: files under Midterm rather than Other. Longest first, so "final project"
#: is not read as a final.
CATEGORY_WORDS: list[tuple[str, GradeCategory]] = [
    ("participation", GradeCategory.PARTICIPATION),
    ("assignment", GradeCategory.ASSIGNMENT),
    ("midterm", GradeCategory.MIDTERM),
    ("project", GradeCategory.PROJECT),
    ("final", GradeCategory.FINAL),
    ("quiz", GradeCategory.QUIZ),
    ("lab", GradeCategory.LAB),
]


def route(parsed: Parsed) -> OmniboxKind:
    """Which module the line belongs to. Ordered, and the order is the rule."""
    if parsed.score is not None and parsed.max_score is not None:
        return OmniboxKind.GRADE
    if parsed.amount is not None:
        return OmniboxKind.EXPENSE
    return OmniboxKind.TASK


def match_named(title: str, names: dict[str, object]) -> tuple[object | None, str]:
    """Find a known name inside the leftover text and take it out.

    Longest name first, so "Emergency Savings" is not matched as "Savings" and
    left looking like a deposit into the wrong pot. Returns what was found and
    the title with that phrase removed, because a name that has been understood
    should not also be left in the description.
    """
    lowered = title.lower()
    for name in sorted(names, key=len, reverse=True):
        needle = name.lower()
        at = lowered.find(needle)
        if at == -1:
            continue
        # Only on a word boundary: "art" must not match inside "started".
        before_ok = at == 0 or not lowered[at - 1].isalnum()
        after = at + len(needle)
        after_ok = after == len(lowered) or not lowered[after].isalnum()
        if not (before_ok and after_ok):
            continue

        remainder = f"{title[:at]} {title[after:]}"
        return names[name], " ".join(remainder.split())

    return None, title


def default_account(db: Session, user_id: uuid.UUID) -> AccountModel | None:
    """Where an expense lands when the line does not say.

    The first spending account, because that is what day-to-day money comes out
    of; failing that, whichever account comes first.
    """
    accounts = (
        db.query(AccountModel)
        .filter(AccountModel.user_id == user_id, AccountModel.archived.is_(False))
        .all()
    )
    if not accounts:
        return None

    accounts.sort(key=lambda account: (account.position, account.name))
    spending = [account for account in accounts if account.kind == "spending"]
    return spending[0] if spending else accounts[0]


def grade_category_for(title: str) -> GradeCategory:
    lowered = title.lower()
    for word, category in CATEGORY_WORDS:
        if word in lowered:
            return category
    return GradeCategory.OTHER


def build_preview(db: Session, user_id: uuid.UUID, text: str) -> OmniboxPreview | None:
    """Read one line and say exactly what filing it would do."""
    if not user_exists(db, user_id):
        return None

    parsed = parse(text)
    kind = route(parsed)
    title = parsed.title

    course = None
    unmatched = None
    if parsed.course_code:
        course = resolve_course(db, user_id, parsed.course_code)
        if course is None:
            # Never swallow text that was not used.
            unmatched = parsed.course_code
            title = f"{parsed.course_code} {title}".strip()

    common = {
        "text": text,
        "kind": kind,
        "matched": parsed.matched,
        "on_date": parsed.on_date,
        "course_id": course.id if course else None,
        "course_code": course.code if course else None,
        "unmatched_course": unmatched,
    }

    if kind == OmniboxKind.GRADE:
        return _grade_preview(parsed, title, course, common)
    if kind == OmniboxKind.EXPENSE:
        return _expense_preview(db, user_id, parsed, title, common)
    return _task_preview(parsed, title, course, common)


def _grade_preview(parsed: Parsed, title: str, course, common) -> OmniboxPreview:
    category = grade_category_for(title)
    name = title or category.value

    if course is None:
        return OmniboxPreview(
            **common, title=name, score=parsed.score, max_score=parsed.max_score,
            grade_category=category.value, can_create=False,
            summary=f"A {parsed.score:g}/{parsed.max_score:g} mark, but no course to put it in",
            reason=(
                # Upper-cased for the message only. The code stays as typed
                # wherever it is put back into the text, since that is the
                # student's own wording.
                f'No course matches "{common["unmatched_course"].upper()}".'
                if common["unmatched_course"]
                else "Start the line with a course code, like COSC 121."
            ),
        )

    return OmniboxPreview(
        **common, title=name, score=parsed.score, max_score=parsed.max_score,
        grade_category=category.value, can_create=True,
        summary=f"{course.code} · {name} · {parsed.score:g}/{parsed.max_score:g} ({category.value})",
    )


def _expense_preview(db: Session, user_id: uuid.UUID, parsed: Parsed, title: str, common) -> OmniboxPreview:
    accounts = {
        account.name: account
        for account in db.query(AccountModel).filter(
            AccountModel.user_id == user_id, AccountModel.archived.is_(False)
        ).all()
    }
    named_account, title = match_named(title, accounts)

    categories = {
        category.name: category
        for category in db.query(SpendCategoryModel).filter(
            SpendCategoryModel.user_id == user_id, SpendCategoryModel.archived.is_(False)
        ).all()
    }
    named_category, remainder = match_named(title, categories)

    account = named_account or default_account(db, user_id)
    # A line that is only a category -- "groceries 40" -- still deserves a
    # description, and the category name is the honest one.
    description = remainder or (named_category.name if named_category else "") or title

    if account is None:
        return OmniboxPreview(
            **common, title=description, amount=parsed.amount, can_create=False,
            summary=f"${parsed.amount:.2f}, but there is nowhere to put it",
            reason="Add an account on the Budget page first.",
        )

    when = parsed.on_date or date.today()
    label = f"${parsed.amount:.2f} from {account.name}"
    if named_category:
        label += f" · {named_category.name}"
    # The course was resolved from the same line, so say so -- otherwise the
    # expense silently acquires a course the preview never mentioned.
    if common.get("course_code"):
        label += f" · {common['course_code']}"

    return OmniboxPreview(
        **{**common, "on_date": when},
        title=description or "Expense",
        amount=parsed.amount,
        account_id=account.id,
        account_name=account.name,
        category_id=named_category.id if named_category else None,
        category_name=named_category.name if named_category else None,
        can_create=True,
        summary=f"{description or 'Expense'} · {label}",
    )


def _task_preview(parsed: Parsed, title: str, course, common) -> OmniboxPreview:
    minutes = parsed.minutes
    if minutes is not None and not (1 <= minutes <= MAX_ESTIMATED_MINUTES):
        minutes = None

    if not title.strip():
        return OmniboxPreview(
            **common, title="", estimated_minutes=minutes, can_create=False,
            summary="Nothing here to make a task from",
            reason="Add what it is you have to do.",
        )

    parts = [title]
    if course is not None:
        parts.append(course.code)
    if parsed.on_date:
        parts.append(parsed.on_date.isoformat())

    return OmniboxPreview(
        **common, title=title, estimated_minutes=minutes, can_create=True,
        summary=" · ".join(parts),
    )


def file_it(db: Session, user_id: uuid.UUID, text: str):
    """Create whatever the line describes, through the owning module's service.

    Built from the same preview the client showed, so what lands is exactly what
    was on screen -- two readings of one line could otherwise drift apart
    between the keystroke and the submit.
    """
    preview = build_preview(db, user_id, text)
    if preview is None:
        return None

    if not preview.can_create:
        raise ValueError(preview.reason or "That line could not be filed")

    if preview.kind == OmniboxKind.GRADE:
        grade = add_grade(db, user_id, preview.course_id, GradeCreate(
            name=preview.title,
            category=GradeCategory(preview.grade_category),
            score=preview.score,
            max_score=preview.max_score,
            due_date=None,
        ))
        return OmniboxResult(
            kind=preview.kind, id=grade.id, course_id=preview.course_id,
            summary=preview.summary, preview=preview,
        )

    if preview.kind == OmniboxKind.EXPENSE:
        transaction = create_transaction(db, user_id, TransactionCreate(
            kind=TransactionKind.EXPENSE,
            account_id=preview.account_id,
            amount=preview.amount,
            description=preview.title,
            occurred_on=preview.on_date or date.today(),
            category_id=preview.category_id,
            # The course was already resolved for the preview and then thrown
            # away here, so "textbook cpsc 210 $80" filed the money but lost
            # what it was for.
            course_id=preview.course_id,
        ))
        if transaction is None:
            raise ValueError("That account no longer exists")
        return OmniboxResult(
            kind=preview.kind, id=transaction.id, summary=preview.summary, preview=preview,
        )

    task = create_task(db, user_id, TaskCreate(
        title=preview.title,
        notes=None,
        due_date=preview.on_date,
        due_time=None,
        estimated_minutes=preview.estimated_minutes,
        course_id=preview.course_id,
        tags=[],
    ))
    return OmniboxResult(
        kind=preview.kind, id=task.id, course_id=preview.course_id,
        summary=preview.summary, preview=preview,
    )
