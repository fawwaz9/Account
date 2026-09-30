# Settings: three tabs, and the bug that has to go first

> **Status: planned, not started.** Written 2026-09-30 against `c81da5a`.
> The standing design note for this area is
> [design/users-and-auth.md](design/users-and-auth.md); read that for how
> preferences work. Read this for what is being changed and in what order.

## What was asked

Verbatim, from `whats_next.txt`:

> Make the whole password section side to side with the account section. There
> should be academic, calender and financial settings. They should only show up
> when they are selected one at a time. Default is academic. The other options
> are beside it. Gold underline under the setting that is currently being shown.
> Add under here suggestions for what to be in each.

So: two cards side by side at the top, a tab strip under them, one panel at a
time, Academic first, gold underline on the active tab. Plus suggestions for the
contents, which are in **Phase 3**.

## Decisions taken

Agreed before planning, so the reasoning is not re-litigated later:

- **One Save per tab, and switching tabs keeps unsaved edits.** State lifts to
  the page so a half-typed Academic form survives a look at Calendar. Nothing
  saves behind your back and nothing is discarded.
- **The Financial tab holds the budget setup that is already configuration** —
  Income split and Edit categories — rather than new preferences invented to
  fill it. Their modals stay exactly as they are; only the entry points move.
- **`timezone` is the only new preference exposed.** Of the seven with no
  control, it is the only one anything reads. The other six stay hidden and the
  audit records why, because a control that does nothing is worse than no
  control.

Taken here rather than asked, each a one-liner if you disagree:

- **The study window moves from Academic to Calendar.** `study_day_start`,
  `study_day_end` and `min_free_block_minutes` exist only to decide which gaps
  between classes are worth offering as free blocks. That is a calendar feature;
  it sits under Academic today because Academic was the only form there was.
- **A real ARIA tablist**, not the Calendar page's `aria-pressed` button group.
  These are tabbed panels, so `role="tablist"` / `role="tab"` /
  `aria-selected` / `role="tabpanel"` with arrow-key movement between tabs. The
  gold underline is the visual half of the same thing.
- **The tab does not persist.** "Default is academic" is taken literally: every
  visit opens on Academic.

---

# Phase 0 — the bug that blocks everything

**Saving Settings today silently resets your timezone.** This is not a risk in
the plan; it is happening in production now, and the per-tab save model cannot
be built on top of it.

## What happens

`UserUpdate.preferences` is typed `UserPreferences | None`, and **every field of
`UserPreferences` has a default**. So a patch that names six fields is parsed
into a complete thirteen-field model, and `model_dump(mode="json")` emits all
thirteen. The merge in `update_user` is then
`{**stored, **thirteen_fields_including_defaults}` — which overwrites every
preference the form did not mention with its default value.

The merge carries this comment, which is correct about the danger and wrong
about being protected from it:

> Preferences are a JSON column, so a partial patch must merge rather than
> replace -- otherwise setting one preference silently clears the rest.

The merge is there. The schema defeats it, because what arrives is never partial.

## Proof

Run against a throwaway SQLite database, never `data/app.db`:

```
BEFORE  timezone=America/Vancouver  credit_target=150
fields the client sent: 6
fields the schema will dump: 13
AFTER   timezone=America/Regina  credit_target=120

*** timezone WAS SILENTLY RESET ***
```

## Why it has gone unnoticed

Six of the seven affected preferences are read by nothing, so resetting them
changes nothing observable. The seventh is `timezone`, and **the default is the
owner's real zone**, so resetting it to `America/Regina` is invisible to the one
person using the app in earnest. It would not be invisible to anyone else:
`timezone` decides when reminders fire (`reminder_service.local_now`) and
whether a task counts as finished early or late
(`timing_service.local_completion_date`).

## Why it blocks the tabs specifically

The chosen model is one Save per tab. With three tabs each sending its own
subset, **saving Calendar would reset everything Academic owns, and vice versa.**
The feature is not merely harder with this bug present — it is incoherent.

## The fix

A patch type whose fields are genuinely optional, dumped with `exclude_unset`:

```python
class UserPreferencesPatch(BaseModel):
    """Every field optional, so an unmentioned preference is left alone.

    Separate from UserPreferences because that model's job is the opposite --
    fill in every default so a reader never sees a missing key. One model
    cannot do both, and the attempt is what reset people's timezones.
    """
    timezone: str | None = None
    # ... one per field, all None
```

`UserUpdate.preferences` becomes `UserPreferencesPatch | None`, and the merge
dumps with `exclude_unset=True` so only what was actually sent is merged. The
validators move across with the fields they guard.

**Mutation test it** (`shipping.md` step 3): drop `exclude_unset=True` and the
regression test must fail. If it passes either way it is testing nothing, which
is how this bug survived having a comment written about it.

---

# Phase 1 — Account and Password, side by side

`.settingsGrid` is `display: grid; gap: 16px; max-width: 520px` — a single
520px column holding three stacked cards. Two changes:

- The grid becomes two columns at width, one column below roughly 760px. Account
  and Password are both short; side by side they read as "who you are and how you
  get in", which is one subject.
- The tab section spans the full width underneath, as its own block rather than a
  third grid cell.

> ### The page-width guard already covers this, and Settings is already the
> ### shape it prescribes
>
> Checked rather than assumed. `pageWidth.test.ts` derives its class list from
> the markup — every class appearing in a `className="container ..."` — so it
> needs no extending. And `SettingsPage`'s container carries no companion class:
> the width sits on `.settingsGrid`, a child, which is exactly what the test's
> own docstring prescribes:
>
> > To genuinely clamp a page, put the width on an inner wrapper that does not
> > also carry `container`.
>
> **So widening `.settingsGrid` is safe, and the rule is what not to do:** do not
> add a width-bearing class to the `container` div itself. That is the tie that
> made the budget page narrow — `.budgetPage { max-width: 980px }` had never
> applied until a build change flipped it and it suddenly did. Keep the number on
> `.settingsGrid` and the guard stays green because there is nothing to break.

---

# Phase 2 — the tab strip

## Markup

```jsx
<div className="settingsTabs" role="tablist" aria-label="Settings sections">
  {TABS.map((tab) => (
    <button
      key={tab.id}
      role="tab"
      id={`tab-${tab.id}`}
      aria-selected={active === tab.id}
      aria-controls={`panel-${tab.id}`}
      tabIndex={active === tab.id ? 0 : -1}
      className={active === tab.id ? "settingsTab settingsTabActive" : "settingsTab"}
      onClick={() => setActive(tab.id)}
    >
      {tab.label}
    </button>
  ))}
</div>
```

`tabIndex={-1}` on the inactive tabs is not decoration: a tablist takes **one**
tab stop, and arrow keys move within it. Without it a keyboard user tabs through
three buttons to reach the panel.

## The gold underline

`border-bottom: 2px solid var(--gold)` on `.settingsTabActive`, with the
inactive tabs carrying a transparent border of the same width so nothing shifts
by two pixels when you click.

> **The underline must not be the only signal.** Audit #60 is open against
> `Sectors` for conveying an overdrawn account by the minus sign alone, and the
> accessibility pass already closed one finding for conveying account kind by
> colour alone. So the active tab also gets brighter text and heavier weight.
> `aria-selected` covers screen readers; this covers everyone who cannot pick
> gold out from grey.

## State

```jsx
const [active, setActive] = useState<TabId>("academic");
```

One value. Every field's state stays lifted at the page level exactly as it is
today, which is what makes "keep edits across a tab switch" free — the panels are
conditionally *rendered*, but the state they bind to never unmounts.

Render with `hidden` rather than `&&` so each panel keeps its DOM node and its
`role="tabpanel"` identity:

```jsx
<div role="tabpanel" id="panel-academic" aria-labelledby="tab-academic"
     hidden={active !== "academic"}>
```

---

# Phase 3 — what goes in each tab

The suggestions that were asked for. Everything marked **exists** is already
built and only moves; everything marked **new** needs work, and says how much.

## Academic — the default tab

| Setting | Status |
|---|---|
| Current school year | **exists**, stays |
| Current semester | **exists**, stays |
| The year your first year began | **exists**, stays, keep the suggestion button |
| Credits required for your degree | **exists**, stays |
| Default target grade | **exists**, stays |
| Show CGPA | **exists**, stays |

Worth considering, none assumed:

- **Archived-course visibility by default.** Courses can be archived and the
  lists take a flag; whether archived work shows by default is a preference
  today expressed by clicking, every time.
- **What "at risk" means.** The risk bands that order the task list are constants
  in the code. Naming the threshold here would make the badge explicable.

## Calendar

| Setting | Status |
|---|---|
| **Time zone** | **new**, and the whole point — see Phase 4 |
| Study hours, start and end | **exists**, moves from Academic |
| Shortest useful gap | **exists**, moves from Academic |
| Blocked periods | **exists** as a modal on the Calendar page; add its entry point here too |

Worth considering:

- **Default calendar view**, month or week. Currently `useState("month")` on
  every visit. Cheap, genuinely useful, and needs one new preference key plus a
  read at mount — the only suggestion here that is nearly free.
- **Whether shifts show on the calendar.** They are events, so they always do.
  Someone with a heavy job week may want the study view without them.

## Financial

| Setting | Status |
|---|---|
| Income split across accounts | **exists** as `IncomeSplitModal` on the Budget page; entry point moves here |
| Edit categories | **exists** as `CategoriesModal`; entry point moves here |

Both are configuration that happens to live on the page where it is used. Moving
the *buttons* costs nothing — the modals, their state and their tests stay where
they are. Leave a route to them on the Budget page as well if it feels like a
loss; a setting having two doors is not a problem, two settings having one name
is.

Worth considering:

- **A default account for Record spending.** The account page answers this
  itself; the Budget page's Record Money still asks every time.
- **Whether safe-to-spend counts work you have done but not been paid for.** It
  is shown as context today, deliberately never as the headline. Someone
  disciplined might want it in the figure; someone who has been burned wants it
  out. A real preference, with a real argument on both sides.
- **Currency.** Deliberately *not* suggested as a setting yet: see Phase 4.

---

# Phase 4 — `timezone`, and the six that stay hidden

## Why only this one

Checked against every consumer in the codebase on 2026-09-30:

| Preference | Read by |
|---|---|
| `timezone` | `timing_service.local_completion_date`, `reminder_service.local_now` |
| `currency` | **nothing** — `money.ts` hardcodes `$` |
| `week_start` | **nothing** — `WEEKDAY_LABELS` is hardcoded Monday-first |
| `theme` | **nothing** — no light theme exists, zero `prefers-color-scheme` rules |
| `date_format` | **nothing** |
| `time_format` | **nothing** — `hourLabel` hardcodes am/pm |
| `default_reminder_minutes_before` | **nothing** — reminders carry an explicit `remind_at` |

Six controls that changed nothing would be six lies on a settings page, and the
page would be worse for having them. They stay out, and **audit #58 is amended**
to say this: the finding as written says seven preferences lack a control, which
reads as seven things to add. One is a bug to fix; six are features that were
never built.

> **`week_start` carries a live inconsistency worth recording while we are
> here.** `UserPreferences.week_start` defaults to `SUNDAY`, and
> `WEEKDAY_LABELS` is hardcoded `["Mon"..."Sun"]`. The stored default already
> contradicts the rendered week. Making it real means changing `startOfWeek` and
> `weekdayIndex`, whose index the recurrence engine's `byday` codes depend on —
> a change to date arithmetic with its own tests, not a settings field.

## The control

A `<select>`, not a text input. A free-text IANA zone is a field where a typo is
a 400 and a plausible wrong answer is a silent bias.

```js
const ZONES = Intl.supportedValuesOf?.("timeZone") ?? FALLBACK_ZONES;
```

`Intl.supportedValuesOf` is the right source and needs a fallback: a short
`FALLBACK_ZONES` list covering Canadian zones plus UTC, since the app's audience
is one university. Offer the browser's own guess
(`Intl.DateTimeFormat().resolvedOptions().timeZone`) as a suggestion button, the
way the first-year field already offers one — evidence presented, not applied.

Say what it affects, because it is not obvious: **reminder times and the
early/late figures**. Per the standing preference for explanation on demand, that
goes behind a `(?)` rather than becoming another line of muted text under the
field.

## Error mapping

The validator raises `ValueError` on an unknown zone. Confirm the user route maps
that to **400**, not 500 — the audit has closed three findings of exactly this
shape, and a `<select>` makes it unreachable from the UI but not from the API.

---

# The traps this will walk into

- **A new stylesheet changes CSS emission order.** Settings currently imports
  `login.css` and nothing else. A new `settings.css` — which the one-stylesheet-
  per-area convention wants — reorders the emitted bundle, and `cssCodeSplit:
  false` preserves the *contents* of the CSS and not its *order*. That is
  precisely the fault that made the budget page narrow. **Diff the built
  stylesheet by order, not just by content**, and check any two rules of equal
  specificity that target the same element. See `shipping.md` step 14.
- **Class-name collisions across features.** `.categoryList` was used by both
  `WhereItWent` and `GradeCategoryColumn`, and whichever emitted later won —
  which broke the grades page. New names here (`settingsTabs`, `settingsTab`,
  `settingsTabActive`, `settingsPanel`) must be checked against every other
  stylesheet, and `classCollisions.test.ts` extended to cover them.
- **`aria-busy` and pending states.** Three Save buttons means three requests
  that need to look like they are happening. `PlannedSpend`'s scoped `aria-busy`
  is the pattern; the standing ask is that a click feel like a click.
- **`refreshUser()` after every save** rebuilds the `user` object, and ten data
  hooks depend on `user?.id` specifically so that does not re-fetch the world.
  Do not reintroduce a dependency on the whole object.

---

# Tests

**Phase 0**, backend, beside the existing user tests:

- A patch naming one preference leaves every other stored preference untouched.
  **Mutation: remove `exclude_unset=True` and watch it fail.**
- A patch naming nothing at all changes nothing.
- An unknown IANA zone is a 400, not a 500.
- Saving the Academic fields does not reset `timezone` — the literal case above,
  named as the regression it is.

**Phases 1–3**, frontend:

- `pageWidth.test.ts` needs **no change** — it derives its class list from the
  markup. Just keep the width off the `container` div's own class list and it
  stays green. Run it anyway; it is the thing that would notice if you did not.
- `classCollisions.test.ts` extended with the new class names.
- `SettingsTabs.test.tsx`: exactly one tab has `aria-selected="true"`; the
  inactive panels are `hidden`; arrow keys move selection; the default is
  Academic. Plus a control asserting a tab click changes the selection at all, so
  the "only one" clauses cannot pass vacuously.
- **Edits survive a tab switch** — type into Academic, switch to Calendar, switch
  back, assert the typing is still there. This is the decision that was taken, so
  it gets the test.

Note what no test here can see: jsdom has no layout engine and no cascade, so
nothing in this list can catch the side-by-side layout being wrong or the gold
underline not applying. Those are read off the built stylesheet or looked at.

---

# Verification and deploy

1. `npm test && ./node_modules/.bin/tsc --noEmit && npm run build`, and `pytest`.
2. Exercise Phase 0 against a **copy** of `data/app.db` — `VACUUM INTO`, never
   `cp`; point `DATABASE_URL` at the copy **before importing anything** and
   assert the engine URL is the copy. Count rows before and after.
3. **No new table and no new column**, so no schema step is owed. `preferences`
   is an existing JSON column and `UserPreferencesPatch` is a request shape, not
   storage. If that changes, step 11 applies.
4. This is an addition, so **schema → API → `main`**. Phase 0 is a backend change
   and must be live before the frontend sends a partial patch — an old API given
   a partial payload fills in defaults, which is the bug.
5. Verify the frontend by **content and by chunk**; Settings is a lazy route, so
   its strings land in its own chunk, and a 200 on a missing asset is Pages
   serving `index.html`.
6. Then `docker builder prune -f`, images first if any are being cleared.

---

# Risks

| Risk | Handling |
|---|---|
| Per-tab saves clobber each other | Phase 0, mutation-tested, shipped to the API before the UI |
| Widening the grid re-runs the budget-page width fault | Width stays on `.settingsGrid`, never on the `container` div; the guard derives its own class list and already covers it |
| A new stylesheet reorders the cascade | Diff the built CSS by order; `shipping.md` step 14 |
| New class names collide with another feature | `classCollisions.test.ts` extended |
| The tab strip is a div soup to a screen reader | Real tablist, one tab stop, arrow keys, `aria-selected`, tested |
| Gold underline invisible to some readers | Weight and brightness change too, not colour alone |
| Six dead preferences get exposed to "finish" #58 | Recorded in the audit as features never built, not gaps in a form |
| Moving the study window confuses someone mid-term | Nothing changes about what it does; only which tab it is under |

---

# Deliberately not in scope

Each is a feature with its own shape, and the last thing that grew sideways got
rolled back:

- A light theme, and the `theme` preference that would drive it.
- `currency` reaching `formatMoney`, which is every money figure in the app.
- `week_start` reaching `startOfWeek`, which the recurrence engine depends on.
- Notification settings beyond what `useReminders` already does — there is no
  scheduler and no push, and the banner says so.
- Account deletion. The endpoint exists, has never had a UI, and putting one on a
  settings page is a decision about a thirty-day grace period, not a form field.
