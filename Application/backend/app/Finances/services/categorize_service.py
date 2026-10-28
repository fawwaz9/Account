"""Suggest a spending category for an expense, from the user's own habits first.

Four layers, each consulted only when the one before has nothing confident to
say: the user's own merchant map (every expense they have categorised), the
shared merchant map (Phase 3 item 4: what 3 or more people agree a merchant is),
a short hand-kept list of Canadian merchants, and naive Bayes over the user's
history. The shared map and the list only ever name one of the user's own
categories, by name. Below the confidence bar nothing is suggested. Nothing here
reads another user's rows: the shared map is read through its floor. CSV import
and the omnibox use it.
"""

import math
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app._database import aggregates
from app._database.models import SpendCategoryModel, TransactionModel
from app.Finances.services.forecast_service import merchant_key

LEARNED, SHARED, RULE, BAYES = "learned", "shared", "rule", "bayes"

#: A merchant you have split between categories is only suggested when one of
#: them holds this share of your past choices.
MAP_AGREEMENT = 0.8
#: Naive Bayes speaks only above this probability, and only with this much
#: history to have learned from.
BAYES_CONFIDENCE = 0.75
BAYES_MIN_ROWS = 10

#: keyword -> category names it belongs under, in preference order. Matched as
#: whole words against the merchant name, most specific first ("uber eats"
#: before "uber"). A contested merchant -- Costco is groceries for one person
#: and household for the next -- is deliberately absent.
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("uber eats", ("Eating out", "Restaurants", "Food", "Dining")),
    ("skipthedishes", ("Eating out", "Restaurants", "Food", "Dining")),
    ("doordash", ("Eating out", "Restaurants", "Food", "Dining")),
    ("tim hortons", ("Eating out", "Coffee", "Restaurants", "Food")),
    ("starbucks", ("Eating out", "Coffee", "Restaurants", "Food")),
    ("blenz", ("Eating out", "Coffee", "Restaurants", "Food")),
    ("mcdonald", ("Eating out", "Restaurants", "Food", "Dining")),
    ("subway", ("Eating out", "Restaurants", "Food", "Dining")),
    ("a&w", ("Eating out", "Restaurants", "Food", "Dining")),
    ("safeway", ("Groceries", "Food")),
    ("save on foods", ("Groceries", "Food")),
    ("save-on-foods", ("Groceries", "Food")),
    ("superstore", ("Groceries", "Food")),
    ("no frills", ("Groceries", "Food")),
    ("t&t", ("Groceries", "Food")),
    ("whole foods", ("Groceries", "Food")),
    ("sobeys", ("Groceries", "Food")),
    ("loblaws", ("Groceries", "Food")),
    ("freshco", ("Groceries", "Food")),
    ("translink", ("Transportation", "Transport", "Travel")),
    ("compass", ("Transportation", "Transport", "Travel")),
    ("lyft", ("Transportation", "Transport", "Travel")),
    ("uber", ("Transportation", "Transport", "Travel")),
    ("evo", ("Transportation", "Transport", "Travel")),
    ("modo", ("Transportation", "Transport", "Travel")),
    ("esso", ("Transportation", "Gas", "Transport")),
    ("shell", ("Transportation", "Gas", "Transport")),
    ("petro canada", ("Transportation", "Gas", "Transport")),
    ("petro-canada", ("Transportation", "Gas", "Transport")),
    ("chevron", ("Transportation", "Gas", "Transport")),
    ("impark", ("Transportation", "Parking", "Transport")),
    ("easypark", ("Transportation", "Parking", "Transport")),
    ("bc hydro", ("Utilities", "Bills")),
    ("fortisbc", ("Utilities", "Bills")),
    ("telus", ("Utilities", "Phone", "Bills")),
    ("rogers", ("Utilities", "Phone", "Bills")),
    ("koodo", ("Utilities", "Phone", "Bills")),
    ("fido", ("Utilities", "Phone", "Bills")),
    ("freedom mobile", ("Utilities", "Phone", "Bills")),
    ("public mobile", ("Utilities", "Phone", "Bills")),
    ("shoppers drug mart", ("Health/medical", "Health", "Pharmacy")),
    ("london drugs", ("Health/medical", "Health", "Pharmacy")),
    ("pharmacy", ("Health/medical", "Health", "Pharmacy")),
    ("ubc bookstore", ("School fees", "School", "Education", "Books")),
    ("goodlife", ("Sports", "Fitness", "Gym")),
    ("sport chek", ("Sports", "Fitness")),
    ("ikea", ("Home", "Household", "Furniture")),
    ("home depot", ("Home", "Household")),
    ("canadian tire", ("Home", "Household")),
    ("netflix", ("Subscriptions", "Entertainment", "Personal")),
    ("spotify", ("Subscriptions", "Entertainment", "Personal")),
]


@dataclass(frozen=True)
class Suggestion:
    """A suggested category for one expense, and which layer produced it.

    Attributes:
        category_id: The suggested category; None to ask.
        source: "learned", "shared", "rule" or "bayes"; None with no suggestion.
    """

    category_id: uuid.UUID | None
    source: str | None = None


NONE = Suggestion(None)
"""The empty suggestion: no category, so the person is asked."""


def _words(key: str) -> list[str]:
    """Return a merchant key's words of two or more letters (and "&"), for Bayes."""
    return [word for word in re.findall(r"[a-z&]+", key) if len(word) >= 2]


def _rule_target(key: str, by_name: dict[str, uuid.UUID]) -> uuid.UUID | None:
    """Return the user's category a curated rule names for a merchant key, or None.

    The first rule whose keyword appears as whole words decides; if the user has none
    of its category names, nothing is suggested.
    """
    padded = f" {key} "
    for keyword, names in RULES:
        if f" {keyword} " in padded:
            for name in names:
                if name.lower() in by_name:
                    return by_name[name.lower()]
            return None  # the right rule, but you have no such category
    return None


class Categorizer:
    """Category suggestions trained once, per request, on the user's own expenses.

    Args:
        db: Open database session.
        user_id: Whose categories and history to learn from.

    Attributes:
        active: Ids of the user's unarchived categories.
        by_name: Lower-cased category name to id.
        map: Merchant key to how often each category was chosen for it.
        word_counts: Per category, how often each merchant word appeared.
        class_rows: Per category, how many expenses it holds.
        vocabulary: Every merchant word seen.
        trained: How many categorised expenses were learned from.
    """

    def __init__(self, db: Session, user_id: uuid.UUID):
        """Load the user's categories and learn from their categorised expenses."""
        categories = (
            db.query(SpendCategoryModel)
            .filter(SpendCategoryModel.user_id == user_id, SpendCategoryModel.archived.is_(False))
            .all()
        )
        self.active = {category.id for category in categories}
        self.by_name = {category.name.lower(): category.id for category in categories}

        rows = (
            db.query(TransactionModel.description, TransactionModel.category_id)
            .filter(
                TransactionModel.user_id == user_id,
                TransactionModel.kind == "expense",
                TransactionModel.category_id.isnot(None),
            )
            .all()
        )
        self.map: dict[str, Counter] = defaultdict(Counter)
        self.word_counts: dict[uuid.UUID, Counter] = defaultdict(Counter)
        self.class_rows: Counter = Counter()
        for description, category_id in rows:
            if category_id not in self.active:
                continue
            key = merchant_key(description)
            if not key:
                continue
            self.map[key][category_id] += 1
            self.class_rows[category_id] += 1
            self.word_counts[category_id].update(_words(key))
        self.vocabulary = {word for counts in self.word_counts.values() for word in counts}
        self.trained = sum(self.class_rows.values())
        self._db = db
        #: Merchant key to the shared map's category name, or None once asked.
        self._shared: dict[str, str | None] = {}

    def prefetch(self, descriptions) -> None:
        """Read the shared map for many descriptions in one call, before suggesting.

        Args:
            descriptions: The descriptions about to be suggested for.
        """
        keys = {merchant_key(d) for d in descriptions} - set(self._shared) - {""}
        found = aggregates.merchant_categories(self._db, list(keys))
        for key in keys:
            self._shared[key] = found.get(key)

    def _shared_target(self, key: str) -> uuid.UUID | None:
        """Return the user's category the shared map names for a merchant key, or None."""
        if key not in self._shared:
            self.prefetch([key])
        name = self._shared.get(key)
        return self.by_name.get(name) if name else None

    def suggest(self, description: str | None) -> Suggestion:
        """Suggest a category for an expense description.

        Args:
            description: The expense's description, as typed or imported.

        Returns:
            The user's own past choice when one category holds at least 80% of it,
            else the shared map's category if the user has one by that name, else a
            curated rule's category, else a Bayes guess at 75% confidence or more,
            else no suggestion.
        """
        key = merchant_key(description)
        if not key:
            return NONE

        seen = self.map.get(key)
        if seen:
            category_id, hits = seen.most_common(1)[0]
            if hits / sum(seen.values()) >= MAP_AGREEMENT:
                return Suggestion(category_id, LEARNED)

        shared = self._shared_target(key)
        if shared is not None:
            return Suggestion(shared, SHARED)

        ruled = _rule_target(key, self.by_name)
        if ruled is not None:
            return Suggestion(ruled, RULE)

        return self._bayes(key)

    def _bayes(self, key: str) -> Suggestion:
        """Return the naive Bayes guess for a merchant key, or nothing below the bar."""
        words = [word for word in _words(key) if word in self.vocabulary]
        if self.trained < BAYES_MIN_ROWS or not words:
            return NONE
        size = len(self.vocabulary)
        scores = {}
        for category_id, rows in self.class_rows.items():
            counts = self.word_counts[category_id]
            total = sum(counts.values())
            score = math.log(rows / self.trained)
            for word in words:
                score += math.log((counts[word] + 1) / (total + size))
            scores[category_id] = score
        best = max(scores, key=scores.get)
        peak = scores[best]
        probability = 1 / sum(math.exp(score - peak) for score in scores.values())
        return Suggestion(best, BAYES) if probability >= BAYES_CONFIDENCE else NONE
