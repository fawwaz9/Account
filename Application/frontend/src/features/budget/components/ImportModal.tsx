import { useMemo, useState } from "react";
import Modal from "../../../shared/components/Modal";
import { commitImport, previewImport } from "../api";
import { ImportMapping, ImportPreview, ImportSummary } from "../types";
import { formatMoney } from "../money";

interface ImportModalProps {
  readonly userId: string;
  readonly accountId: string;
  readonly accountName: string;
  readonly onClose: () => void;
  /** Called after rows are written, so the page can reload. */
  readonly onImported: (summary: ImportSummary) => void;
}

/**
 * Bring a bank's CSV into one account -- Phase 1 item 7.
 *
 * Three steps, and nothing is written until the last: pick a file, check what
 * it would add (columns guessed, duplicates unticked, unreadable lines shown
 * and left out), then import the ticked lines. The columns are always shown
 * and always editable, because a guess about which column is the amount is the
 * one mistake that would put wrong money in the ledger.
 */
export default function ImportModal({ userId, accountId, accountName, onClose, onImported }: ImportModalProps) {
  const [filename, setFilename] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [shown, setShown] = useState<ImportPreview | null>(null);
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState<"reading" | "importing" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<ImportSummary | null>(null);

  async function read(csv: string, mapping: ImportMapping | null) {
    setBusy("reading");
    setError(null);
    try {
      const result = await previewImport(userId, accountId, csv, mapping);
      setShown(result);
      // New rows start ticked; duplicates and unreadable lines do not.
      setTicked(new Set(result.rows.filter((row) => row.status === "new").map((row) => row.line)));
    } catch (err) {
      setShown(null);
      setError(err instanceof Error && err.message ? err.message : "Couldn't read that file.");
    } finally {
      setBusy(null);
    }
  }

  async function choose(file: File | undefined) {
    if (!file) return;
    setFilename(file.name);
    const csv = await readFile(file);
    setText(csv);
    await read(csv, null);
  }

  function remap(change: Partial<ImportMapping>) {
    if (!shown || text === null) return;
    void read(text, { ...shown.mapping, ...change });
  }

  async function importTicked() {
    if (!shown || text === null || ticked.size === 0) return;
    setBusy("importing");
    setError(null);
    try {
      const summary = await commitImport(
        userId, accountId, text, shown.mapping, [...ticked].sort((a, b) => a - b), filename,
      );
      setDone(summary);
      onImported(summary);
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Couldn't import those rows.");
    } finally {
      setBusy(null);
    }
  }

  const totals = useMemo(() => {
    let moneyIn = 0;
    let moneyOut = 0;
    for (const row of shown?.rows ?? []) {
      if (!ticked.has(row.line) || row.amount === null) continue;
      if (row.amount > 0) moneyIn += row.amount;
      else moneyOut -= row.amount;
    }
    return { moneyIn, moneyOut };
  }, [shown, ticked]);

  if (done) {
    return (
      <Modal title="Imported" onClose={onClose}>
        <p role="status">
          {done.row_count} {done.row_count === 1 ? "row" : "rows"} added to {accountName}.
        </p>
        {done.subscription_candidates ? (
          <p className="small-text muted">
            {done.subscription_candidates} repeating{" "}
            {done.subscription_candidates === 1 ? "charge looks" : "charges look"} like a subscription.
            Review them under Subscriptions on the Budget page.
          </p>
        ) : null}
        <p className="small-text muted">You can undo this import from the account page.</p>
        <div className="flex justify-end gap-3 pt-4">
          <button type="button" className="buttons" onClick={onClose}>Done</button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title={`Import into ${accountName}`} onClose={onClose} panelClassName="importPanel">
      <label className="importFile">
        <span className="small-text muted">A CSV exported from your bank</span>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => void choose(event.target.files?.[0])}
          disabled={busy !== null}
          aria-label="CSV file"
        />
      </label>

      {busy === "reading" && <p className="small-text muted" role="status">Reading…</p>}
      {error && <p className="small-text error" role="alert">{error}</p>}

      {shown && (
        <>
          <Columns preview={shown} onChange={remap} disabled={busy !== null} />

          <p className="small-text importCounts">
            {shown.new_count} new · {shown.duplicate_count} already in this account ·{" "}
            {shown.error_count} couldn't be read
          </p>

          <div className="importTable">
            <table>
              <thead>
                <tr>
                  <th scope="col" aria-label="Import" />
                  <th scope="col">Date</th>
                  <th scope="col">Description</th>
                  <th scope="col">Amount</th>
                  <th scope="col"></th>
                </tr>
              </thead>
              <tbody>
                {shown.rows.map((row) => (
                  <tr key={row.line} className={row.status === "error" ? "importRowError" : undefined}>
                    <td>
                      <input
                        type="checkbox"
                        checked={ticked.has(row.line)}
                        disabled={row.status === "error" || busy !== null}
                        onChange={(event) => {
                          const next = new Set(ticked);
                          if (event.target.checked) next.add(row.line);
                          else next.delete(row.line);
                          setTicked(next);
                        }}
                        aria-label={`Import line ${row.line}`}
                      />
                    </td>
                    <td>{row.on_date ?? ""}</td>
                    <td>{row.description}</td>
                    <td className={row.amount !== null && row.amount < 0 ? "importOut" : undefined}>
                      {row.amount !== null ? formatMoney(row.amount) : ""}
                    </td>
                    <td className="small-text muted">{row.status === "new" ? "" : row.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="importFooter">
            <span className="small-text">
              {ticked.size} ticked · {formatMoney(totals.moneyIn)} in · {formatMoney(totals.moneyOut)} out
            </span>
            <button
              type="button"
              className="buttons"
              onClick={importTicked}
              disabled={busy !== null || ticked.size === 0}
            >
              {busy === "importing" ? "Importing…" : `Import ${ticked.size} ${ticked.size === 1 ? "row" : "rows"}`}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}

/** Which column is which. Always shown, always editable: the guess decides the money. */
function Columns({
  preview,
  onChange,
  disabled,
}: {
  readonly preview: ImportPreview;
  readonly onChange: (change: Partial<ImportMapping>) => void;
  readonly disabled: boolean;
}) {
  const { mapping, columns } = preview;
  const split = mapping.amount === null;
  const pick = (label: string, value: number | null, apply: (index: number) => void) => (
    <label className="importPick">
      <span className="small-text muted">{label}</span>
      <select
        className="--input"
        value={value ?? ""}
        onChange={(event) => apply(Number(event.target.value))}
        disabled={disabled}
        aria-label={label}
      >
        {columns.map((name, index) => (
          <option key={index} value={index}>{name || `Column ${index + 1}`}</option>
        ))}
      </select>
    </label>
  );

  return (
    <fieldset className="importColumns" disabled={disabled}>
      <legend className="small-text muted">Columns</legend>
      {pick("Date", mapping.date, (date) => onChange({ date }))}
      {pick("Description", mapping.description[0], (index) => onChange({ description: [index] }))}
      <label className="importPick">
        <span className="small-text muted">Amounts</span>
        <select
          className="--input"
          value={split ? "split" : "one"}
          onChange={(event) => onChange(event.target.value === "split"
            ? { amount: null, debit: mapping.amount ?? 0, credit: mapping.amount ?? 0 }
            : { amount: mapping.debit ?? 0, debit: null, credit: null })}
          aria-label="Amounts"
        >
          <option value="one">One column, signed</option>
          <option value="split">Money out and money in apart</option>
        </select>
      </label>
      {split ? (
        <>
          {pick("Money out", mapping.debit, (debit) => onChange({ debit }))}
          {pick("Money in", mapping.credit, (credit) => onChange({ credit }))}
        </>
      ) : (
        pick("Amount", mapping.amount, (amount) => onChange({ amount }))
      )}
      <label className="importPick">
        <span className="small-text muted">Dates like 03/04</span>
        <select
          className="--input"
          value={mapping.date_order}
          onChange={(event) => onChange({ date_order: event.target.value as "mdy" | "dmy" })}
          aria-label="Date order"
        >
          <option value="mdy">Month first</option>
          <option value="dmy">Day first</option>
        </select>
      </label>
      <label className="importCheck">
        <input
          type="checkbox"
          checked={mapping.invert}
          onChange={(event) => onChange({ invert: event.target.checked })}
        />
        <span className="small-text">Purchases show as positive (flip the signs)</span>
      </label>
      {preview.date_order_assumed && (
        <p className="small-text importWarn">
          Every date reads both ways. Check the first few against your statement.
        </p>
      )}
    </fieldset>
  );
}

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}
