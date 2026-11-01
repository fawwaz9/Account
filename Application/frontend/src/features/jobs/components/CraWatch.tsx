import { SelfEmployment } from "../types";
import { formatMoney } from "../../budget/money";
import { shortDate } from "../../../shared/utils/dateUtils";

/** What the GST/HST level says, in words. */
const GST_WORDS = {
  under: "Under the small-supplier line.",
  approaching: "Approaching the line: past 80% of $30,000.",
  over: "Over $30,000: you're no longer a small supplier, and have to register and charge GST/HST.",
} as const;

/**
 * The CRA rules read against what you recorded: GST/HST over four quarters, CPP at both
 * halves, and the instalment dates. Information with its sources, never advice.
 */
export default function CraWatch({ year }: { readonly year: SelfEmployment }) {
  const { gst, cpp, instalments } = year;
  const share = Math.min(100, (gst.four_quarter_total / gst.threshold) * 100);
  const peak = Math.max(1, ...gst.quarters.map((q) => q.total));

  return (
    <section className="seCard" aria-label="Tax rules">
      <h2 className="seHeading">GST/HST watch</h2>
      <p className="small-text">
        {formatMoney(gst.four_quarter_total)} invoiced over the last four quarters, of the {formatMoney(gst.threshold, { whole: true })} line.
      </p>
      <div className="seMeter" role="img" aria-label={`${Math.round(share)}% of $30,000`}>
        <span className={`seMeterFill seLevel-${gst.level}`} style={{ width: `${share}%` }} />
      </div>
      <p className={`small-text seLevelText seLevelText-${gst.level}`}>{GST_WORDS[gst.level]}</p>
      <ul className="seQuarters">
        {gst.quarters.map((q) => (
          <li key={q.starts_on}>
            <span className="seQuarterBar" style={{ height: `${Math.max(2, (q.total / peak) * 40)}px` }} aria-hidden="true" />
            <span className="seQuarterLabel">{q.label}</span>
            <span className="seQuarterTotal">{formatMoney(q.total, { whole: true })}</span>
          </li>
        ))}
      </ul>
      <p className="small-text muted">
        By the date you invoiced; the current quarter to date. Exempt services (some tutoring, for one)
        don&rsquo;t count. Ride-share and taxi drivers register from the first dollar, whatever the total.
      </p>

      <h2 className="seHeading">CPP on it</h2>
      <p className="small-text">
        About <strong>{formatMoney(cpp.total)}</strong> for {year.year}: self-employed, you pay both halves
        ({cpp.rate}% instead of {cpp.rate / 2}%) on net income above the {formatMoney(cpp.exemption, { whole: true })} exemption,
        up to {formatMoney(cpp.ceiling, { whole: true })}{cpp.second > 0 ? `, then ${cpp.second_rate}% to ${formatMoney(cpp.second_ceiling, { whole: true })}` : ""}.
      </p>
      {cpp.employment_gross > 0 && (
        <p className="small-text muted">
          Your recorded job pay ({formatMoney(cpp.employment_gross, { whole: true })}) uses the exemption and the
          ceiling first; its own CPP came off your cheques.
        </p>
      )}
      {cpp.figures_year !== year.year && (
        <p className="small-text muted">Using {cpp.figures_year}&rsquo;s figures, the latest the app knows.</p>
      )}

      <h2 className="seHeading">Instalments</h2>
      <p className="small-text">
        If your tax owing at filing is over {formatMoney(instalments.threshold, { whole: true })} this year, and was in
        either of the two years before, CRA expects it in quarterly instalments
        {instalments.next_due ? <>; the next date is <strong>{shortDate(instalments.next_due)}</strong></> : ""}.
        Dates: {instalments.dates.map((d) => shortDate(d)).join(", ")}. ($1,800 in Quebec.)
      </p>
      <p className="small-text muted">
        The app doesn&rsquo;t estimate your income tax: that takes your whole return. CRA sends an instalment
        reminder if it expects you to pay them.
      </p>

      <p className="small-text muted">{year.note}</p>
      <ul className="seSources small-text">
        {year.sources.map((s) => (
          <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.label}</a></li>
        ))}
      </ul>
    </section>
  );
}
