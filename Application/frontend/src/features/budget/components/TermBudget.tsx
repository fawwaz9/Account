import { useEffect, useRef, useState } from "react";
import { fetchTermBudget } from "../api";
import { TermBudget as Term } from "../types";
import { formatMoney } from "../money";
import { useAuth } from "../../../app/auth/AuthContext";

interface TermBudgetProps {
  /** Bumped by the page when something changes, to refetch. */
  readonly nonce: number;
}

/**
 * What this term has cost, over the term's own dates.
 *
 * A calendar month is the wrong unit for a student. Tuition lands once and
 * textbooks land in the first fortnight; neither is a monthly rhythm, so a
 * month-by-month view shows one enormous September and four quiet months.
 *
 * The span comes from Grades, which is the only part of the app that knows when
 * a term runs — and knows it per course, so a year-long course stretches the
 * span. That is correct: it is genuinely how long you are buying books for.
 */
export default function TermBudget({ nonce }: TermBudgetProps) {
  const { user } = useAuth();
  const [term, setTerm] = useState<Term | null>(null);
  const latestRequest = useRef(0);

  useEffect(() => {
    if (!user) return;
    const ticket = ++latestRequest.current;
    let cancelled = false;

    fetchTermBudget(user.id)
      .then((result) => {
        if (!cancelled && ticket === latestRequest.current) setTerm(result);
      })
      .catch(() => {
        if (!cancelled && ticket === latestRequest.current) setTerm(null);
      });

    return () => { cancelled = true; };
  }, [user, nonce]);

  if (!term) return null;

  // Nothing to measure and no courses at all is not worth a panel telling you
  // so on the Budget page — that belongs on Grades, where you would fix it.
  if (!term.can_measure && term.dated_courses + term.undated_courses === 0) {
    return null;
  }

  const progress = term.days_total > 0
    ? Math.round((term.days_elapsed / term.days_total) * 100)
    : 0;

  return (
    <section className="termBudget">
      <div className="termBudgetHead">
        <h2>{term.term_name}</h2>
        {term.can_measure && (
          <span className="termBudgetDates">
            day {term.days_elapsed} of {term.days_total}
          </span>
        )}
      </div>

      {!term.can_measure ? (
        <p className="termBudgetEmpty">{term.reason}</p>
      ) : (
        <>
          <div className="termBudgetTrack" aria-hidden="true">
            <div className="termBudgetFill" style={{ width: `${progress}%` }} />
          </div>

          <div className="termBudgetFigures">
            <div>
              <span className="termBudgetLabel">Spent</span>
              <strong>{formatMoney(term.spent)}</strong>
            </div>
            <div>
              <span className="termBudgetLabel">Received</span>
              <strong>{formatMoney(term.received)}</strong>
            </div>
            <div>
              <span className="termBudgetLabel">Net</span>
              <strong className={term.net < 0 ? "termBudgetNegative" : undefined}>
                {formatMoney(term.net)}
              </strong>
            </div>
            <div>
              <span className="termBudgetLabel">On courses</span>
              <strong>{formatMoney(term.on_courses)}</strong>
            </div>
          </div>

          {/* Said plainly, because the span is the term rather than the weeks
              you are actually taught in, and a textbook bought the week before
              classes start is inside it.

              This line used to read "measured from 2 of 6 courses — the rest
              carry no term dates", which described the old rule: the span was
              assembled from whichever courses happened to be dated. It is no
              longer true of anything, and with most courses undated it would
              have shown that claim permanently. */}
          <p className="termBudgetNote">
            Measured over the whole term, not the teaching weeks — so spending
            in the days either side of classes is counted.
          </p>

          {term.by_category.length > 0 && (
            <ul className="termBudgetCategories">
              {term.by_category.slice(0, 6).map((entry) => (
                <li key={entry.category_name}>
                  <span>{entry.category_name}</span>
                  <span>{formatMoney(entry.actual)}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
