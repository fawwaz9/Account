import { useId, useState } from "react";

/** A help mark's accessible label, panel content and tone. */
interface HelpTipProps {
  /** Accessible name for the mark; required, since the glyph alone says nothing. */
  readonly label: string;
  readonly children: React.ReactNode;
  /** "warning" draws a red "!" instead of "?" for something that needs doing; default "help". */
  readonly tone?: "help" | "warning";
}

/**
 * A "?" button toggling a short explanation panel in the flow beneath it; Escape closes it.
 * Click rather than hover, so it works on touch screens and from the keyboard.
 */
export default function HelpTip({ label, children, tone = "help" }: HelpTipProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <span
      className="helpTip"
      onKeyDown={(event) => {
        if (event.key !== "Escape" || !open) return;
        // Stopped here so Escape does not also close a dialog this happens to be
        // rendered inside. The innermost thing that is open should be the thing
        // that closes.
        event.stopPropagation();
        setOpen(false);
      }}
    >
      <button
        type="button"
        className={tone === "warning" ? "helpTipMark helpTipWarning" : "helpTipMark"}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={label}
        onClick={() => setOpen((was) => !was)}
      >
        {/* The glyph is decoration; `aria-label` above carries the meaning. */}
        <span aria-hidden="true">{tone === "warning" ? "!" : "?"}</span>
      </button>

      {open && (
        <span className="helpTipPanel" id={panelId} role="note">
          {children}
        </span>
      )}
    </span>
  );
}
