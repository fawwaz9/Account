"""Prerequisite rules: the tree, its typed form, and whether you meet one.

Phase 2 items 4 and 7 (fact D). A rule is a small JSON tree:

* ``{"course": "CPSC 210"}``, optionally with ``"min_grade": 64``
* ``{"credits": 6, "subject": "MATH", "level": 100}`` -- six credits of MATH
  100-level; subject and level are each optional
* ``{"all": [...]}`` and ``{"any": [...]}``

Codes are stored without a campus suffix ("CPSC 210", not "CPSC_V 210"): a
rule is about which course, and the catalogue row it hangs on already says
which campus. Anything a tree cannot hold -- year standing, "or permission of
the instructor" -- goes in the note beside it, never in here.

The typed form is what a person writes and what the page shows::

    CPSC 210 and one of MATH 200, MATH 217
    (CPSC 121 or MATH 220) and 6 credits of MATH 1xx
    CPSC 210 with 64%

``and`` (or a comma at the top level) joins everything; ``or`` binds tighter,
so "A or B and C" is "(A or B) and C". ``one of`` / ``all of`` take a
comma-separated list that runs to the next ``and``, a closing parenthesis, or
the end.

**Advisory only** (Phase 2 D3). Evaluating a rule says met, on track or not
met. Nothing in the app is ever disabled by the answer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Bounds on a rule's size: generous for any real calendar entry, small enough
#: that a pasted essay is refused rather than stored.
MAX_DEPTH = 4
MAX_NODES = 40
MAX_CHILDREN = 12
MAX_TEXT = 300

CODE = re.compile(r"^([A-Za-z]{2,5})(?:_[A-Za-z])?\s*(\d{3}[A-Za-z]?)$")
LEVEL = re.compile(r"^(\d)xx$", re.IGNORECASE)


class RuleError(ValueError):
    """A rule, or its typed form, that cannot be used. The message says why."""


def normal_code(text: str) -> str | None:
    match = CODE.match(text.strip())
    if match is None:
        return None
    return f"{match.group(1).upper()} {match.group(2).upper()}"


def code_key(code: str) -> tuple[str, int] | None:
    """(subject, number) for comparing with your courses, letter suffix aside --
    the same reading as the degree audit's ``parse_code``."""
    normal = normal_code(code)
    if normal is None:
        return None
    subject, number = normal.split(" ")
    return subject, int(number[:3])


# --------------------------------------------------------------------------
# Checking a tree
# --------------------------------------------------------------------------

def validate(rule: Any) -> dict:
    """The rule, normalised, or RuleError. Used on everything stored."""
    count = [0]

    def walk(node: Any, depth: int) -> dict:
        count[0] += 1
        if count[0] > MAX_NODES:
            raise RuleError(f"A rule can have at most {MAX_NODES} parts")
        if depth > MAX_DEPTH:
            raise RuleError(f"A rule can nest at most {MAX_DEPTH} deep")
        if not isinstance(node, dict) or len(node) == 0:
            raise RuleError("Each part of a rule must be an object")
        keys = set(node)
        if keys <= {"course", "min_grade"} and "course" in keys:
            code = normal_code(str(node["course"])) if isinstance(node["course"], str) else None
            if code is None:
                raise RuleError(f"{node['course']!r} is not a course code")
            out: dict = {"course": code}
            if node.get("min_grade") is not None:
                grade = node["min_grade"]
                if isinstance(grade, bool) or not isinstance(grade, (int, float)) or not 0 < grade <= 100:
                    raise RuleError("A minimum grade is a percentage above 0 and at most 100")
                out["min_grade"] = float(grade)
            return out
        if keys <= {"credits", "subject", "level"} and "credits" in keys:
            credits = node["credits"]
            if isinstance(credits, bool) or not isinstance(credits, (int, float)) or not 0 < credits <= 150:
                raise RuleError("Credits must be a number above 0")
            out = {"credits": float(credits)}
            if node.get("subject") is not None:
                subject = node["subject"]
                if not isinstance(subject, str) or not re.fullmatch(r"[A-Za-z]{2,5}", subject):
                    raise RuleError(f"{subject!r} is not a subject")
                out["subject"] = subject.upper()
            if node.get("level") is not None:
                level = node["level"]
                if isinstance(level, bool) or level not in (100, 200, 300, 400, 500, 600):
                    raise RuleError("A level is 100, 200, ... 600")
                out["level"] = int(level)
            return out
        if keys in ({"all"}, {"any"}):
            (kind,) = keys
            children = node[kind]
            if not isinstance(children, list) or not children:
                raise RuleError(f"'{kind}' needs a list of at least one part")
            if len(children) > MAX_CHILDREN:
                raise RuleError(f"A group can hold at most {MAX_CHILDREN} parts")
            parts = [walk(child, depth + 1) for child in children]
            return parts[0] if len(parts) == 1 else {kind: parts}
        raise RuleError(f"Unrecognised part of a rule: {sorted(keys)}")

    return walk(rule, 1)


# --------------------------------------------------------------------------
# The typed form
# --------------------------------------------------------------------------

TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<credits>\d+(?:\.\d+)?)\s+credits?(?:\s+of)?"
    r"|(?P<code>[A-Za-z]{2,5}(?:_[A-Za-z])?\s*\d{3}[A-Za-z]?)\b"
    r"|(?P<level>\dxx)\b"
    r"|(?P<pct>\d+(?:\.\d+)?)\s*%"
    r"|(?P<word>one\s+of|all\s+of|and|or|with|min(?:imum)?)\b"
    r"|(?P<subject>[A-Za-z]{2,5})\b"
    r"|(?P<punct>[(),])"
    r")",
    re.IGNORECASE,
)


def _tokens(text: str) -> list[tuple[str, str]]:
    out, at = [], 0
    text = text.strip()
    while at < len(text):
        match = TOKEN.match(text, at)
        if match is None or match.end() == at:
            raise RuleError(f"Couldn't read the rule from {text[at:at + 20]!r}")
        kind = match.lastgroup
        value = match.group(kind)
        if kind == "word":
            value = re.sub(r"\s+", " ", value.lower())
            value = "min" if value.startswith("min") else value
        out.append((kind, value))
        at = match.end()
    return out


class _Parser:
    def __init__(self, tokens):
        self.tokens, self.at = tokens, 0

    def peek(self, offset=0):
        index = self.at + offset
        return self.tokens[index] if index < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.at += 1
        return token

    def is_word(self, word, offset=0):
        return self.peek(offset) == ("word", word)

    def expr(self):
        parts = [self.or_expr()]
        while self.is_word("and") or self.peek() == ("punct", ","):
            self.take()
            parts.append(self.or_expr())
        return parts[0] if len(parts) == 1 else {"all": parts}

    def or_expr(self):
        parts = [self.atom()]
        while self.is_word("or"):
            self.take()
            parts.append(self.atom())
        return parts[0] if len(parts) == 1 else {"any": parts}

    def items(self):
        parts = [self.or_expr()]
        while self.peek() == ("punct", ","):
            self.take()
            parts.append(self.or_expr())
        return parts

    def atom(self):
        kind, value = self.take()
        if kind is None:
            raise RuleError("The rule ends too early")
        if (kind, value) == ("punct", "("):
            inner = self.expr()
            if self.take() != ("punct", ")"):
                raise RuleError("A '(' is never closed")
            return inner
        if kind == "word" and value in ("one of", "all of"):
            parts = self.items()
            if len(parts) == 1:
                return parts[0]
            return {"any" if value == "one of" else "all": parts}
        if kind == "credits":
            node: dict = {"credits": float(value)}
            if self.peek()[0] == "subject":
                node["subject"] = self.take()[1].upper()
            if self.peek()[0] == "level":
                node["level"] = int(self.take()[1][0]) * 100
            return node
        if kind == "code":
            node = {"course": normal_code(value)}
            grade = self.grade()
            if grade is not None:
                node["min_grade"] = grade
            return node
        raise RuleError(f"Didn't expect {value!r} there")

    def grade(self):
        # "CPSC 210 with 64%", "CPSC 210 (64%)", "CPSC 210 min 64%"
        if self.is_word("with") or self.is_word("min"):
            self.take()
            kind, value = self.take()
            if kind != "pct":
                raise RuleError("'with' needs a percentage after it, like 'with 64%'")
            return float(value)
        if self.peek() == ("punct", "(") and self.peek(1)[0] == "pct" and self.peek(2) == ("punct", ")"):
            self.take()
            value = self.take()[1]
            self.take()
            return float(value)
        return None


def parse_text(text: str) -> dict:
    """The typed form as a tree, validated. RuleError says what is wrong."""
    if not text or not text.strip():
        raise RuleError("The rule is empty")
    if len(text) > MAX_TEXT:
        raise RuleError(f"A rule can be at most {MAX_TEXT} characters")
    parser = _Parser(_tokens(text))
    rule = parser.expr()
    if parser.peek()[0] is not None:
        raise RuleError(f"Didn't expect {parser.peek()[1]!r} there")
    return validate(rule)


def render(rule: dict, nested: bool = False) -> str:
    """A tree in the typed form. ``parse_text(render(r)) == r`` for a valid r."""
    if "course" in rule:
        grade = rule.get("min_grade")
        return rule["course"] + (f" with {grade:g}%" if grade is not None else "")
    if "credits" in rule:
        words = f"{rule['credits']:g} credits"
        if rule.get("subject") or rule.get("level"):
            words += " of"
        if rule.get("subject"):
            words += f" {rule['subject']}"
        if rule.get("level"):
            words += f" {rule['level'] // 100}xx"
        return words
    if "any" in rule:
        parts = rule["any"]
        if all("course" in p or "credits" in p for p in parts):
            text = "one of " + ", ".join(render(p, True) for p in parts)
            return f"({text})" if nested else text
        text = " or ".join(render(p, True) for p in parts)
        return f"({text})" if nested else text
    parts = rule["all"]
    text = " and ".join(render(p, True) for p in parts)
    return f"({text})" if nested else text


# --------------------------------------------------------------------------
# Whether you meet it
# --------------------------------------------------------------------------

MET, ON_TRACK, NOT_MET = "met", "on_track", "not_met"
RANK = {NOT_MET: 0, ON_TRACK: 1, MET: 2}


@dataclass(frozen=True)
class Taken:
    """One thing on your record, as a rule sees it: a course, or an
    equivalence standing in for its sources."""

    label: str
    codes: frozenset[tuple[str, int]]
    credits: float
    #: completed, in_progress or planned (the degree audit's statuses), or
    #: failed: a recorded result under the pass mark.
    status: str
    #: (school year, semester order): when it is or was taken.
    term: tuple[int, int]
    #: The final result, when there is one. None for transfer credit and
    #: equivalences, which carry no grade.
    grade: float | None = None


@dataclass
class Result:
    status: str
    text: str
    #: Why, in words, for a leaf: "CPSC 210 done (82%)", "3 of 6 credits".
    detail: str = ""
    parts: list[Result] = field(default_factory=list)
    #: "all" or "any" for a group; None for a leaf.
    group: str | None = None


def evaluate(rule: dict, record: list[Taken], term: tuple[int, int], kind: str = "prerequisite") -> Result:
    """Whether ``record`` meets ``rule`` for a course taken in ``term``.

    A prerequisite counts only from a term before the course's own; a
    co-requisite may also be the same term. Within that window: completed is
    met; in progress or planned is on track -- it will be met if it goes as
    planned. A minimum grade is checked when the result is known.
    """
    def counts(item: Taken) -> bool:
        return item.term < term or (kind == "corequisite" and item.term == term)

    def best(results: list[Result]) -> Result:
        return max(results, key=lambda r: RANK[r.status]) if results else None

    def leaf_course(node: dict) -> Result:
        key = code_key(node["course"])
        text = render(node)
        candidates = [item for item in record if key in item.codes]
        if not candidates:
            return Result(NOT_MET, text, f"{node['course']} is not on your record")
        timely = [item for item in candidates if counts(item)]
        if not timely:
            return Result(NOT_MET, text, f"{candidates[0].label} is not before this course")
        results = []
        for item in timely:
            if item.status == "failed":
                results.append(Result(NOT_MET, text, f"{item.label} not passed"))
                continue
            if item.status != "completed":
                results.append(Result(ON_TRACK, text, f"{item.label} {item.status.replace('_', ' ')}"))
                continue
            minimum = node.get("min_grade")
            if minimum is not None and item.grade is not None and item.grade < minimum:
                results.append(Result(NOT_MET, text, f"{item.label} done with {item.grade:g}%, {minimum:g}% needed"))
                continue
            shown = f" ({item.grade:g}%)" if item.grade is not None else ""
            results.append(Result(MET, text, f"{item.label} done{shown}"))
        return best(results)

    def leaf_credits(node: dict) -> Result:
        subject, level = node.get("subject"), node.get("level")

        def qualifies(item: Taken) -> bool:
            return any((subject is None or s == subject) and (level is None or level <= n < level + 100)
                       for s, n in item.codes)

        timely = [item for item in record if counts(item) and qualifies(item) and item.status != "failed"]
        done = sum(item.credits for item in timely if item.status == "completed")
        coming = sum(item.credits for item in timely if item.status != "completed")
        need = node["credits"]
        detail = f"{done:g} of {need:g} credits"
        if done >= need:
            return Result(MET, render(node), detail)
        if done + coming >= need:
            return Result(ON_TRACK, render(node), f"{detail}, {coming:g} more under way")
        return Result(NOT_MET, render(node), detail)

    def walk(node: dict) -> Result:
        if "course" in node:
            return leaf_course(node)
        if "credits" in node:
            return leaf_credits(node)
        kind_ = "all" if "all" in node else "any"
        parts = [walk(child) for child in node[kind_]]
        ranks = [RANK[p.status] for p in parts]
        rank = min(ranks) if kind_ == "all" else max(ranks)
        status = next(s for s, r in RANK.items() if r == rank)
        return Result(status, render(node), parts=parts, group=kind_)

    return walk(rule)
