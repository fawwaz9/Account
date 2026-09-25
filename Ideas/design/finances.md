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
| `term_span`, `term_budget` | `services/tuition_service.py` | a term measured over its fixed dates, from `Grades/utils/terms.py` |
| `preview_tuition`, `record_tuition` | `services/tuition_service.py` | a term priced from a per-credit rate |

## Data model

`accounts` — name, `kind`, `income_share`, `archived`, `position`. User-defined,
because one student's "Savings" is another's "Tuition fund".

`kind` is mostly styling and sensible defaults, with **two** exceptions now:
safe-to-spend counts `spending` accounts only, and `debt` marks money owed. The
column's own comment warns against loading a third meaning onto it — the next
per-account rule wants its own column.

**A `debt` account is not a special case, and that is the design.** Its balance
is the ordinary signed sum of its rows, so it reads negative: buying with the
card is an expense on the account, and paying it down is an ordinary transfer
that moves it toward zero. Nothing anywhere has to know the sign is backwards,
and any total that adds every balance subtracts debt for free. Storing "amount
owed" as a positive figure instead would have meant teaching the balance chart,
the running balance and the money-in/money-out split that this one kind is
different.

### What a new student starts with

`DEFAULT_ACCOUNTS` seeds five pots on first read — Spending, Savings,
Investments and Emergency Savings carrying the income split, plus School at 0%
so adding it takes no cut from the others. It is a **starting point, not a
complete set**, and the shortness is the decision.

A "Money Lent" pot was seeded alongside them for a while. It was removed: now
that accounts are fully creatable, a pot that only some students want is
clutter the rest have to notice and delete, and naming it in the seed quietly
claims that lending is a fixed shape the app understands. It is not — it is one
account among many a student might want, with the name and kind they choose.
The general rule: **seed only what the app itself depends on, and leave the
particular to the person.**

Removing it changes nothing for anyone who already has one. Seeding is lazy and
only runs for a user with no accounts at all, so existing "Money Lent" accounts
keep their balances and history and can be deleted by hand if they are not
wanted.

### Two roles the app cannot do without

The last non-archived **spending** account and the last **savings** account
refuse to be deleted, archived, **or have their kind changed away**. The third
is the one that would have been missed: re-kinding the only spending account to
"other" empties the role exactly as deleting it would.

Archiving counts as removal because `safe_service` filters on `archived` *and*
`kind` — archiving the last spending account makes safe-to-spend report `$0.00`
with nothing on screen to say why, which is a wrong answer that looks exactly
like a right one.

Protection reads the **kind, not the name**, so renaming "Spending" to
"Chequing" keeps it and a student holding three spending accounts may delete any
two. The rule lives in `would_orphan_role`, and `get_accounts` attaches a
`role_locked` flag from the same helper so the client greys the controls out
rather than keeping a second copy of the rule that is free to disagree.

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

## Net worth, and why debt needs no arithmetic

The page used to show `Total:` — a plain client-side sum of every balance. It
counted a credit card as though it were savings and money someone else was
holding as though it were in your pocket, and the **dashboard computed the same sum a second time**, so
there were two copies of a rule free to disagree.

```
net_worth  = sum(balance for a in accounts if a.counts_toward_net_worth)
debt_total = abs(sum(balance for a in accounts if a.kind == "debt"))
```

**`net_worth` is a plain sum, and that is the whole point.** A debt account's
balance is already negative, so it subtracts itself. Subtracting `debt_total`
as well is the one mistake this design invites, and it reports someone 500 in
the black as 500 in the red — there is a test named for it.

`debt_total` reports the same money as a positive magnitude, because "Debt
−1,000" reads as a double negative on screen. It is a component of the figure
above it, not a second answer, so it is rendered smaller.

An account toggled out of the total appears on **neither** line. Money owed *to*
you and money owed *by* you are opposites, and a single "outside net worth"
figure would add them together.

Archived accounts are excluded, matching `get_accounts`, so the headline and the
list below it always move together.

**Any account may be taken out of the total.** This was first built so that only
an `other` account could, on the reasoning that money lent out was the real
case and that hiding a savings account would let the headline be quietly
falsified. That
was reversed deliberately: it trades a rule the student has to be told about for
a judgement they are better placed to make, and a joint account or a pot held for
somebody else is just as real a case as money lent out.

The default is still to count, so nothing is hidden unless it is chosen.

**It is independent of `kind`, and must stay that way.** Excluding a spending
account from net worth does not change what safe-to-spend counts — *what am I
worth* and *what can I spend before payday* are different questions, and one
setting quietly moving two figures is the kind of coupling that makes a number
untrustworthy. There is a test asserting exactly that.

> **The migration is the interesting part.** Every older boolean in
> `ADDED_COLUMNS` is written `BOOLEAN NOT NULL DEFAULT 0`, which **Postgres
> rejects** — *"column is of type boolean but default expression is of type
> integer"*. `counts_toward_net_worth` is the first entry there that will ever
> run as an `ALTER` against Postgres, because every older one predates Supabase,
> whose tables `create_all` built from the models with nothing left to add. It
> uses `DEFAULT true`, which both dialects accept. Verified on a real
> `postgres:17-alpine` with rows present, and on a copy of `data/app.db` with
> the column dropped first.

## Editing the split and the categories

Both had complete server-side CRUD from the day they were written, and no UI.
Three of the four category endpoints had **never been called by anything**, and
`updateCategory` did not exist in the client at all.

**The income split is edited as a whole**, not one account at a time. The
per-account field in Edit account still works and writes the same column, but
these are *ratios*: a share of 50 means 55.6% of income when the shares total
90, and a single field cannot say so. The modal shows every account with what
its share actually comes to.

Saving is one PATCH per changed account. A partial failure is survivable here
and only here — because income divides by ratio, whatever lands is still a
valid split, just not the intended one. What is **not** survivable is every
share at zero, which leaves a deposit nowhere to go; `record_deposit` has always
refused that, and the modal refuses to save it rather than walking you into it.

> **Making rename reachable exposed a bug that had never been reachable.**
> `create_category` checks for a clash with `ilike`; `update_category` checked
> nothing. Two faults sat behind that, and one comparison closes both: the
> unique index `uq_spend_categories_user_name` is **case-sensitive**, so
> renaming to "groceries" beside "Groceries" slipped past it and produced two
> categories nobody could tell apart — while an exact-case collision *did* hit
> the index and escaped as an `IntegrityError`, reaching the client as a 500.
> That is the same shape as the concurrent-registration fault in the audit's
> low tier, one module along.

**"Where it went" always renders now.** It used to be conditional on there being
spend, which hid both of these controls in exactly the month you are most likely
to want them, and made the page silently switch between one and two columns.
The section takes its two actions as optional props: the account detail page
reuses it for a single account, where page-level controls would be out of place.

## Budgeting a category, on the account it is spent from

A limit is keyed on **(account, category)**, and that pair is the whole design.

The first attempt put the limit on the category alone and showed it on the
account page, so a limit covering every account was judged against one account's
share of the spending -- a category split across two accounts always looked
safely under budget. It shipped, and was rolled back the same day. Keying on the
pair means the limit and the spending it is measured against cover the same
money.

**Standing, with a per-month override.** `account_category_limits` holds what
this account means to spend here every month; `account_category_month_limits`
holds one row per month that *differs*, and only those. A category budgeted the
same all year has no override rows at all, which is what lets moving the
standing figure move every month nobody overrode.

> **Two tables rather than a nullable `month` on one.** A unique index cannot
> enforce "at most one standing row" when the distinguishing column is NULL --
> Postgres and SQLite both treat NULLs as distinct, so
> `UNIQUE (user, account, category, month)` would accept two standing limits for
> the same pair. Partial indexes could say it, but they are dialect-specific and
> `ensure_indexes` walks the metadata generically. Two tables, each with a unique
> index that actually holds.

> **A row of 0 is a real instruction**, and its absence is the only thing that
> means "no limit". `planned_for_account` in `Finances/utils/limits.py`
> therefore keys on the list being **empty**, not on its sum being falsy -- a
> single limit of 0 is a budget of nothing, and the obvious check reads a
> deliberately closed account as merely unbudgeted.

**The account's target is the sum of its category limits, when it has any.**
Otherwise it keeps the figure typed into Planned spend. That condition is what
protects Savings and Money Lent, which carry real targets and would never be
itemised by "Groceries" -- deriving unconditionally would report both as
budgeting nothing. The rule returns the figure and a `planned_is_derived` flag
together, so no caller can take one without the other and describe a derived
number as a manual one.

Both screens read that one function, so they cannot report different targets for
the same account. On the budget page a derived figure is shown but **not
editable**: one number with two places to set it is the shape where whichever
you edited last quietly wins.

**The budget page shows no category limits at all**, and that absence is load-
bearing rather than an oversight. It spans every account, so a per-account limit
has nothing there to be judged against. It falls out of the data -- the summary
leaves `limit` as None and such a row renders as a plain total.

**Both deletes clear the table first.** `account_category_limits` has foreign
keys to accounts and categories, so leaving rows behind is not untidiness, it is
an integrity error on the delete. Mutation-testing proved it: removing the
cleanup fails with `FOREIGN KEY constraint failed` rather than merely littering.

> **The category row layout has now broken twice for the same reason.** Giving a
> row a bar gives it a third child, and `justify-content` on the `li` only works
> while a row is exactly two spans. The `li` stacks and `.categoryTop` spreads,
> which is what `.plannedRow` / `.plannedTop` has always done one panel up.
> `categoryRow.test.ts` pins it, because jsdom has no layout engine and no test
> that renders the component can see this class of fault.

## Recording spending from an account

The account page has its own **Record spending** button, and it has no account
picker. On an account's own page the account is not a question, and a picker
there is a field that is always already answered and can only be answered
wrongly.

Its own dialog rather than a fifth mode on `AddMoneyModal`, which carries four
modes, a debounced deposit preview and two account pickers -- locking that down
would mean threading conditionals through all of it to switch most of it off.
Expense only: income and transfers belong to the budget page where both accounts
are in view, and a deposit splits across every account by income share, which is
the opposite of what the dialog means.

"Where it went" on this page now renders even with nothing spent, because limits
are set from inside it and hiding it on an empty month hid the only way to
budget an account that has not been used yet. That is the same reasoning that
made the budget page's copy unconditional.

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

## Subscription audit

Read-only, no tables: every call re-groups the ledger fresh, so there is
nothing to keep in sync when a transaction is corrected later.

Only an **expense with no `recurring_id`** can be a finding — one already tied
to a standing instruction is already known, and the whole feature exists to
surface the ones that are not. Rows group by a normalised description (lower
case, trailing reference number stripped, so "NETFLIX.COM 8842119" and
"netflix.com #33012" are the same run), and a group is reported only once it
clears three separate guards together: it has repeated **3 or more times**, its
amounts sit within **10% of their own median**, and the gaps between charges all
land inside one rhythm — 6–8 days, 13–16, or 25–35. All three numbers live in
one dict beside the function, the same convention as `CRUNCH_WEIGHTS`, so they
are tunable without reading the matching logic.

**One gap outside the window fails the whole run**, not just that one date. A
subscription that skipped a month cannot be told apart, from here, from two
unrelated charges that happened to repeat twice with the same description — and
the false positive is worse than the miss, since the point of this feature is
to be trusted enough to act on.

**Each finding carries its own standing instruction, already filled in** —
amount, account, category, cadence and a starting date one period past the last
charge — because a pattern nobody can act on is trivia, not an audit.

**Confirming has to do two things, not one.** Creating the `RecurringCreate` is
the obvious half; the second is tagging the charges that made the case with the
new rule's id. Skip it and the fix does not hold: those rows still carry no
`recurring_id`, so the exact same run qualifies as a pattern again on the very
next read and the card never goes away. `POST /subscriptions/confirm` takes the
occurrence ids straight from the card that was shown — never re-derived from the
description on the server — so confirming a stale card cannot tag the wrong
rows. Mutation-tested: skipping the tagging step is caught by a dedicated test,
separately from the one confirming the rule itself gets created correctly.

Verified against a copy of the real ledger: 37 real expenses, nothing repeats
description three times, zero findings — the right answer, not a gap in the
detector.

## Still open

Reimbursement state, and who and when for money lent out — on whichever
account the student keeps it in, since there is no longer a seeded pot for it.

Account ordering is stored (`position`) and has no editor, so the grid order is
whatever creation produced. Worth a drag handle only if the list gets long.
