import { useState } from "react";
import { Link } from "react-router-dom";
import HelpTip from "../../shared/components/HelpTip";

/** One first-run step: a label, where it is done, and whether it is. */
export interface Step {
  readonly id: string;
  readonly label: string;
  /** Route that does the step. */
  readonly to: string;
  readonly done: boolean;
}

/** What the dashboard knows that decides each step. */
export interface StepInputs {
  readonly termSet: boolean;
  /** Saved Settings time zone. */
  readonly zone: string | undefined;
  /** The browser's zone; when unknown, the zone step counts as done. */
  readonly browserZone: string | undefined;
  readonly courseCount: number;
  readonly hasMoney: boolean;
  readonly hasWeek: boolean;
}

/**
 * The five first-run steps, each done once the thing it asks for exists.
 * The zone step is done when the saved zone matches the browser's.
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

/** localStorage key remembering a dismissed checklist, per user. */
function hiddenKey(userId: string) {
  return `account.getStarted.hidden.${userId}`;
}

/** Whether this user dismissed the checklist in this browser; false if storage is refused. */
function readHidden(userId: string): boolean {
  try {
    return window.localStorage.getItem(hiddenKey(userId)) === "1";
  } catch {
    return false;
  }
}

/** Props for the first-run checklist. */
interface GetStartedProps {
  readonly userId: string;
  readonly steps: readonly Step[];
}

/**
 * Dashboard first-run checklist linking to each step; gone once all are done or it is dismissed.
 * Dismissal is remembered per user in this browser only.
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
