import { CategorySpend } from "../types";
import { formatMoney } from "../money";

interface WhereItWentProps {
  readonly entries: readonly CategorySpend[];
}

export default function WhereItWent({ entries }: WhereItWentProps) {
  return (
    <section className="categorySpend">
      <div className="sectionHeading">
        <h2>Where it went</h2>
      </div>

      <ul className="categoryList">
        {entries.map((entry) => (
          <li key={entry.category_id ?? "none"}>
            <span>{entry.category_name}</span>
            <span className="categoryAmount">{formatMoney(entry.actual)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
