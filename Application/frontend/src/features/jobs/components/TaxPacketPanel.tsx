import { useEffect, useState } from "react";
import { fetchTaxPacket } from "../api";
import { TaxPacket } from "../types";
import { formatMoney } from "../../budget/money";
import { today } from "../../../shared/utils/dateUtils";

/** Props for the tax packet panel. */
interface Props {
  readonly userId: string;
  readonly nonce: number;
}

/** The year people are filing for on a given day: last year until the end of April. */
export function defaultYear(day: string) {
  const [year, month] = day.split("-").map(Number);
  return month <= 4 ? year - 1 : year;
}

/**
 * A calendar year's employment income from recorded cheques, never a T4, with tuition paid.
 * A summary to check against the slips, not tax advice.
 */
export default function TaxPacketPanel({ userId, nonce }: Props) {
  const [year, setYear] = useState(() => defaultYear(today()));
  const [packet, setPacket] = useState<TaxPacket | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    fetchTaxPacket(userId, year)
      .then((found) => { if (!cancelled) setPacket(found); })
      .catch(() => { if (!cancelled) { setPacket(null); setFailed(true); } });
    return () => { cancelled = true; };
  }, [userId, year, nonce]);

  const thisYear = Number(today().slice(0, 4));
  const years = [thisYear, thisYear - 1, thisYear - 2];

  return (
    <section className="taxPacket" aria-label="Tax packet">
      <div className="sectionHeading">
        <h2>Tax packet</h2>
        <label className="small-text">
          <span className="srOnly">Year</span>
          <select value={year} onChange={(event) => setYear(Number(event.target.value))} aria-label="Tax year">
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
      </div>
      {failed && <p className="small-text muted">Couldn&rsquo;t load the tax packet.</p>}
      {packet && packet.employers.length === 0 && packet.tuition_paid === 0 && (
        <p className="small-text muted">No paycheques or tuition recorded for {packet.year}.</p>
      )}
      {packet && (packet.employers.length > 0 || packet.tuition_paid > 0) && (
        <>
          {packet.employers.map((e) => (
            <div key={e.job_name} className="taxEmployer">
              <h3>{e.job_name}{e.employer && e.employer !== e.job_name ? ` · ${e.employer}` : ""}</h3>
              <dl className="taxLines">
                <dt>Gross pay ({e.paycheques} {e.paycheques === 1 ? "cheque" : "cheques"})</dt>
                <dd>{formatMoney(e.gross)}</dd>
                {e.deductions.map((d) => (
                  <div key={d.label} className="taxLine"><dt>{d.label}</dt><dd>{formatMoney(d.amount)}</dd></div>
                ))}
                <dt>Net</dt><dd>{formatMoney(e.net)}</dd>
                {e.cash_tips > 0 && <><dt>Cash tips</dt><dd>{formatMoney(e.cash_tips)}</dd></>}
                {e.other_tips > 0 && <><dt>Tips through payroll</dt><dd>{formatMoney(e.other_tips)}</dd></>}
              </dl>
            </div>
          ))}
          <dl className="taxLines taxTotals">
            <dt>Total gross pay</dt><dd>{formatMoney(packet.gross)}</dd>
            <dt>Income tax</dt><dd>{formatMoney(packet.income_tax)}</dd>
            <dt>CPP</dt><dd>{formatMoney(packet.cpp)}</dd>
            <dt>EI</dt><dd>{formatMoney(packet.ei)}</dd>
            {packet.other_deductions > 0 && <><dt>Other deductions</dt><dd>{formatMoney(packet.other_deductions)}</dd></>}
            {packet.cash_tips > 0 && <><dt>Cash tips</dt><dd>{formatMoney(packet.cash_tips)}</dd></>}
            {packet.tuition_paid > 0 && <><dt>Tuition paid</dt><dd>{formatMoney(packet.tuition_paid)}</dd></>}
          </dl>
        </>
      )}
      <p className="small-text muted">
        From what you recorded, for cheques that arrived in that year. Check it against your T4s
        and your school&rsquo;s tuition slip; this is a summary for your records, not tax advice.
      </p>
    </section>
  );
}
