# Finances

## Context

The ledger, and everything that reads it. Its defining rule is narrow and worth
stating first: **a transaction is money that entered or left an account.**
Nothing else belongs in it.

That rule is what makes the module trustworthy and what makes the other modules
work. A bursary reduces a tuition bill and never touches the bank. Income tax
reduces a paycheque and never touches the bank. Both are real, both are recorded,
and neither is a transaction — they live on the record that knows about them, and
only the net reaches the ledger.

**Decisions taken:** accounts are user-defined, not an enum; income splits across
accounts by a share each one carries; a transfer is two rows tied by `group_id`;
what money went *on* (category) is separate from which pot it came *from*
(account).

## What it is built from

| Piece | Where | What it does |
|---|---|---|
| `split_income` | `services/deposit_service.py:22` | divide an amount by each account's share, remainder on the largest |
| `record_deposit` | `services/deposit_service.py:62` | one income row per account, one `group_id` |
| `is_money_in` / `is_money_out` | `services/activity_service.py` | direction, including a transfer's two signs |
| `get_budget_summary` | `services/budget_service.py:186` | a month against its targets |
| `run_due` / `upcoming` | `services/recurring_service.py` | standing instructions, written when due |
| `term_span`, `term_budget` | `services/tuition_service.py` | a term measured over its own dates |
| `preview_tuition`, `record_tuition` | `services/tuition_service.py` | a term priced from a per-credit rate |

## Data model

`accounts` — name, `kind` (styling and defaults, not behaviour), `income_share`,
`archived`, `position`. User-defined, because one student's "Savings" is
another's "Tuition fund".

`transactions` — `kind` (income / expense / transfer), amount, `occurred_on`,
`account_id`, and four nullable links that each mean exactly one thing:

- `group_id` — ties a transfer's two halves, or a deposit's several rows
- `category_id` — what it was spent on. Expenses only
- `recurring_id` — the standing instruction that wrote it. **Deliberately not
  `group_id`**: that column already carries two meanings, and a third is what the
  two deposit bugs were made of
- `course_id` — a textbook for CPSC 210. Expenses only, and **not** used by
  tuition

`spend_categories`, `budget_targets` — what money goes on, and the monthly ceiling.

`tuition_payments` + `tuition_deductions` — the pattern the rest of the app
copies. Stores the *rate*, not the total, so two instalments mean entering half
the rate twice. `credits_counted` is stored rather than recomputed because it is
what the bill was for: recomputing it later would rewrite history when a course
is added or dropped.

## The tuition shape, and why everything reuses it

A tuition payment writes **exactly one ledger row**, never one per course.

What a course cost is a *Grades* answer — credits × the term's per-credit rate,
gross — and is not meant to tie out against the ledger, which records the net of
one payment covering a whole term. Fees are mandatory but belong to no course: a
U-Pass is not a cost of CPSC 210, so it is in the ledger line and absent from
every course page.

Deductions — a bursary, a scholarship, a deposit paid earlier — reduce the cheque
without being income. Recording them as income would invent a deposit that never
happened; dropping them would make the total unexplainable. So they sit on the
payment, named, and only the net reaches the ledger.

[jobs.md](jobs.md) is this shape in reverse, and it was a near-mechanical
translation: gross pay, named deductions, only the net in the ledger.

## What was built

Accounts with income shares and a distribute-on-deposit flow; spending categories
and monthly targets; the account page with a balance chart, a flow chart and a
where-it-went breakdown; standing instructions in all four kinds on the shared
recurrence engine; `course_id` on expenses; Pay Tuition; term budget measured
over the term's own dates rather than a calendar month.

## Notes

- **Only money that moved.** If it never entered or left an account, it is not a
  transaction.
- `group_id` means "transfer pair" or "deposit split". Do not give it a third
  meaning.
- A split's parts must sum to the whole. `split_income` puts the rounding
  remainder on the largest share, where a cent is least noticeable.
- Money is float. Round at the boundary, compare with a tolerance.
- A derived ledger row refuses a direct amount edit: a tuition row's amount comes
  from rate × credits, and editing it here would leave the ledger and the course
  pages each saying something different with nothing to choose between them.
- Cascades both ways, tested by mutation. Deleting a tuition row removes the
  payment; deleting the payment removes the row. Only the first half existed
  once, and the orphan kept answering for money that was gone.
- `record_deposit` commits. Anything needing the rows and its own record in one
  transaction must build them itself — see `deposit_rows` in the Jobs module.
- Per-credit rates are additive across a term's payments.

## Safe to spend

The one figure on the budget page that answers a question rather than recording
one, so it leads the page and it is a single headline.

```
safe_now  = spending balances − committed − unfunded earmarks
safe_soon = safe_now + confirmed work not yet paid
```

**The window ends the day before the next cheque**, taken from whichever job's
pay rule produces the soonest one, falling back to month end when no job has a
rule. A rolling thirty days can span two rents or none; a calendar month reports
two days of runway on the 29th. The period you actually have to make money last
is the one before more arrives — and that answer only became available once Jobs
knew about pay schedules.

**Only spending accounts count.** This is the single place `accounts.kind`
drives behaviour rather than styling, and the column itself now says so. Against
real data the difference is stark: roughly $27,800 across every account, against
what is actually in the spending pot.

**Two figures, one headline.** `safe_now` is the answer; `safe_soon` sits under
it as context. A cheque can be late or short — catching that is part of why Jobs
exists — so a headline including unearned money would be optimistic exactly
where being wrong causes an overdraft.

Nothing that has not arrived is ever counted: incoming standing instructions
inside the window are filtered out too, not only unpaid work.

A negative result is reported rather than clamped. Being over-committed is the
most useful thing this figure can say, so it changes colour rather than tone —
and `per_day` goes null, because a daily allowance of minus money is not
guidance.

## Sinking funds

What something costs and when it is due. The monthly figure is
`(target − saved) ÷ months left`, **derived on every read and never stored**: a
stored schedule goes stale the moment a month is missed or the target changes,
and the recovery from either is that same division — so storing it would only be
a second answer able to disagree with the first.

A contribution row exists only once the transfer has happened, for the same
reason a projected payment is not a transaction. Planned contributions have no
row at all.

**Why it cannot double-count.** Safe-to-spend subtracts a fund's contribution
only while it is still a promise. Once transferred, the money is in a savings
account, which safe-to-spend already excludes. Verified end to end on real data:
the safe figure is *identical* either side of a contribution — the earmark drops
to zero exactly as the spending balance falls by the same amount.

A fund past its due date with money still owed asks for the whole remainder
rather than spreading it over one more month, which would quietly move the
deadline. Zero months left is also a division by nothing, so the fallback is
load-bearing rather than cosmetic.

Deleting a fund takes its transfers with it; deleting a transfer clears the
contribution. Both directions are mutation-tested — a fund left claiming money
no longer set aside is the orphaned-tuition-payment fault again.

## Still open a subscription audit reading the ledger for
repeats with no standing instruction behind them; reimbursement state; who and
when on Money Lent.
