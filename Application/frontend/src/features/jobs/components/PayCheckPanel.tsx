import { PayCheck } from "../types";
import { formatMoney } from "../../budget/money";

/** A cheque's check with its working shown: the verdict, each line with its rule, then notes. */
export default function PayCheckPanel({ check }: { readonly check: PayCheck }) {
  const flagged = check.status === "short";
  return (
    <div className={`payCheck${flagged ? " payCheckShort" : ""}`} role="region" aria-label="Cheque check">
      <p className="payCheckSummary">{check.summary}</p>

      {check.lines.length > 0 && (
        <table className="payCheckLines">
          <tbody>
            {check.lines.map((line) => (
              <tr key={line.label}>
                <th scope="row">
                  {line.label}
                  {line.rule && <span className="payCheckRule">{line.rule}</span>}
                </th>
                <td>
                  {line.hours !== null && line.rate !== null
                    ? `${line.hours} h × ${formatMoney(line.rate)}`
                    : ""}
                </td>
                <td>{formatMoney(line.amount)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            {check.expected !== null && (
              <tr>
                <th scope="row">Expected{check.vacation_percent !== null ? ", vacation pay held" : ""}</th>
                <td />
                <td>{formatMoney(check.expected)}</td>
              </tr>
            )}
            {check.expected_with_vacation !== null && (
              <tr>
                <th scope="row">Expected, vacation pay on the cheque</th>
                <td />
                <td>{formatMoney(check.expected_with_vacation)}</td>
              </tr>
            )}
            <tr>
              <th scope="row">On the cheque</th>
              <td />
              <td>{formatMoney(check.actual_gross)}</td>
            </tr>
          </tfoot>
        </table>
      )}

      {check.notes.length > 0 && (
        <ul className="payCheckNotes">
          {check.notes.map((note) => (
            <li key={note} className="small-text muted">{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
