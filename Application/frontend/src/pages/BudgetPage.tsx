import BudgetView from "../features/budget/components/BudgetView";
// The standing-instruction panel reuses the calendar's buttons, form fields
// and recurrence editor, so their styles have to be present here too.
import "../styles/calendar.css";
import "../styles/tasks.css";
import "../styles/budget.css";

/** Budget route: the budget view, with the stylesheets it needs. */
export default function BudgetPage() {
  return <BudgetView />;
}
