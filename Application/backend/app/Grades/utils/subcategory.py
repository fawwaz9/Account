"""Subcategory weights: how a category's weight is shared between its items (D29).

A category is either *even* -- no item carries a `subcategory_weight`, and every
item counts the same whatever it is marked out of -- or *split*: every item carries
one, and together they add up to the category's weight. Nothing in between is
ever stored. The helpers here keep that true through each change that could break
it: an item joins a split category at 0%, an item that leaves gives its weight to
the rest in proportion, and a change to the category's weight scales the split.
Pure: no session, no commit.
"""

#: How far a split's total may sit from the category's weight, in percent,
#: before it is refused. Shares are stored to 2 places, so anything finer is
#: rounding rather than a mistake.
TOLERANCE = 0.01


def members(course, category: str) -> list:
    """Return every grade in a category, dropped ones included.

    A dropped grade keeps its share: the professor dropped the mark, not the item,
    and the rest count for it while it is out.

    Args:
        course: Course row whose `grades` are read.
        category: Category value.

    Returns:
        The category's grades, in the course's order.
    """
    return [g for g in course.grades if g.category == category]


def is_split(items) -> bool:
    """Return whether a category's weight is split, from its members.

    Args:
        items: Every grade in the category.

    Returns:
        True when any of them carries a subcategory weight.
    """
    return any(g.subcategory_weight is not None for g in items)


def share(grade, split: bool) -> float:
    """Return an item's share for averaging within its category.

    Args:
        grade: The grade.
        split: Whether its category is split.

    Returns:
        Its subcategory weight when split (0 for none), else 1 -- every item equal.
    """
    if not split:
        return 1.0
    return grade.subcategory_weight or 0.0


def carries_weight(course, grade) -> bool:
    """Return whether an item can move its category's average at all.

    Args:
        course: The grade's course.
        grade: The grade.

    Returns:
        False only for an item at 0% of a split category.
    """
    return share(grade, is_split(members(course, grade.category))) > 0


def spread(total: float, parts: list[float]) -> list[float]:
    """Return `parts` scaled to add up to `total`, to 2 places, exactly.

    Each part keeps its proportion. Rounding leaves the sum a cent or so out, and
    that remainder goes to the largest part, so the stored split adds up to the
    category's weight to the cent. Parts that are all 0 have no proportion to keep,
    and share the total evenly.

    Args:
        total: What the parts must add up to.
        parts: The current parts, 0 or more each.

    Returns:
        The new parts, in the same order; empty for no parts.
    """
    if not parts:
        return []
    whole = sum(parts)
    if whole > 0:
        scaled = [round(total * part / whole, 2) for part in parts]
    else:
        scaled = [round(total / len(parts), 2) for _ in parts]
    remainder = round(total - sum(scaled), 2)
    if remainder:
        largest = max(range(len(scaled)), key=lambda i: scaled[i])
        scaled[largest] = round(scaled[largest] + remainder, 2)
    return scaled


def rebalance(course, category: str) -> None:
    """Make a split category add up to its weight again, in proportion.

    Called after an item leaves the category and after the category's weight
    changes. An even category is left alone; a category whose weight is now 0 has
    nothing to split, and goes back to even.

    Args:
        course: Course row with its grades and weights loaded; set on the rows, not
            flushed.
        category: Category value.
    """
    items = members(course, category)
    if not is_split(items):
        return
    weight = course.category_weights.get(category, 0.0)
    if weight <= 0:
        for g in items:
            g.subcategory_weight = None
        return
    for g, value in zip(items, spread(weight, [g.subcategory_weight or 0.0 for g in items])):
        g.subcategory_weight = value


def joining_share(course, category: str, exclude=None) -> float | None:
    """Return the subcategory weight a grade takes on joining a category.

    Args:
        course: The course.
        category: The category it joins.
        exclude: A grade to leave out of the check: the one joining, when it is
            already in `course.grades`.

    Returns:
        0.0 in a split category, so the split still adds up and the new item counts
        for nothing until the student changes it; None in an even one.
    """
    others = [g for g in members(course, category) if g is not exclude]
    return 0.0 if is_split(others) else None


def check_split(course, category: str, weights: dict) -> dict:
    """Return a requested split, checked against the category, ready to store.

    Args:
        course: Course row with its grades and weights loaded.
        category: Category value.
        weights: Grade id to its share in percent of the course.

    Returns:
        Grade id to share, rounded to 2 places.

    Raises:
        ValueError: If the category has no weight, the ids are not exactly the
            category's items, a share is negative, or the shares do not add up to
            the category's weight.
    """
    weight = course.category_weights.get(category, 0.0)
    if weight <= 0:
        raise ValueError(f"{category} has no weight to split. Give it a weight first.")
    ids = {g.id for g in members(course, category)}
    if not ids:
        raise ValueError(f"{category} has nothing in it to split.")
    if set(weights) != ids:
        raise ValueError(f"A split needs a weight for every item in {category}, and only those.")
    if any(value < 0 for value in weights.values()):
        raise ValueError("A subcategory weight can't be negative.")
    rounded = {grade_id: round(value, 2) for grade_id, value in weights.items()}
    total = round(sum(rounded.values()), 2)
    if abs(total - weight) > TOLERANCE:
        raise ValueError(
            f"Subcategory weights must add up to {category}'s {weight:g}%; these add up to {total:g}%."
        )
    return rounded
