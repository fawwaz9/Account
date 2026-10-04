import { useState } from "react";
import { Link } from "react-router-dom";
import HelpTip from "../../shared/components/HelpTip";

/** One thing a new student does to get the app working for them. */
export interface Step {
  readonly id: string;
  readonly label: string;
  readonly to: string;
  readonly done: boolean;
}

export interface StepInputs {
  readonly termSet: boolean;
  readonly zone: string | undefined;
  readonly browserZone: string | undefined;
  readonly courseCount: number;
  readonly hasMoney: boolean;
  readonly hasWeek: boolean;
}

/**
 * What "set up" means, derived entirely from data the dashboard already has.
 *
 * Nothing is stored about the checklist itself: a step is done when the thing
 * it asks for exists, so a student who did it some other way -- through the
 * omnibox, say -- is not told to do it again.
 *
 * The time zone step is done when the saved zone matches the browser's. A new
 * account starts on America/Regina, which is right for the first users and
 * wrong for anyone else, and "today" -- what is due, what is overdue -- comes
 * from it everywhere.
 */
export function steps(inputs: StepInputs): Step[] {
  return [
    {
      id: "term",
      label: "Tell it which term you're in",
      to: "/settings?tab=academic",
      done: inputs.termSet,
    },
    {
      id: "zone",
      label: "Check your time zone",
      to: "/settings?tab=calendar",
      done: !inputs.browserZone || inputs.zone === inputs.browserZone,
    },
    {
      id: "courses",
      label: "Add your courses",
      to: "/grades",
      done: inputs.courseCount > 0,
    },
    {
      id: "week",
      label: "Put something on your week: a class time, a shift or a task",
      to: "/calendar",
      done: inputs.hasWeek,
    },
    {
      id: "money",
      label: "Record some money: a balance, a paycheque or an expense",
      to: "/budget",
      done: inputs.hasMoney,
    },
  ];
}

function hiddenKey(userId: string) {
  return `account.getStarted.hidden.${userId}`;
}

function readHidden(userId: string): boolean {
  try {
    return window.localStorage.getItem(hiddenKey(userId)) === "1";
  } catch {
    return false;
  }
}

interface GetStartedProps {
  readonly userId: string;
  readonly steps: readonly Step[];
}

/**
 * The first-run checklist on the dashboard, Phase 0's onboarding item: a new
 * account opens on empty screens, and this turns "where do I start" into five
 * links, each going straight to the place that does the step.
 *
 * Gone once every step is done, or once hidden. Hiding is remembered per user
 * in this browser only -- a convenience, not a setting, so it does not need the
 * server.
 */
export default function GetStarted({ userId, steps: list }: GetStartedProps) {
  const [hidden, setHidden] = useState(() => readHidden(userId));
  const remaining = list.filter((step) => !step.done).length;

  if (hidden || remaining === 0) return null;

  function hide() {
    try {
      window.localStorage.setItem(hiddenKey(userId), "1");
    } catch {
      // Storage refused (private window): it hides for this visit only.
    }
    setHidden(true);
  }

  return (
    <section className="gradeSummary getStarted" aria-labelledby="get-started-title">
      <div className="getStartedHeader">
        <h2 id="get-started-title">
          Get started <span className="getStartedCount">{list.length - remaining} of {list.length}</span>
        </h2>
        <HelpTip label="About this checklist">
          Each step ticks itself off once the thing exists, however you added it. Hide the
          list any time; nothing is lost.
        </HelpTip>
        <button type="button" className="buttons getStartedHide" onClick={hide}>
          Hide
        </button>
      </div>
      <ol className="getStartedList">
        {list.map((step) => (
          <li key={step.id} className={step.done ? "getStartedStep getStartedDone" : "getStartedStep"}>
            <span className="getStartedMark" aria-hidden="true">{step.done ? "✓" : "○"}</span>
            {step.done ? (
              <span>
                {step.label}
                <span className="srOnly"> (done)</span>
              </span>
            ) : (
              <Link to={step.to}>{step.label}</Link>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
