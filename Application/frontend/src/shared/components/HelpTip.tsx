import { useId, useState } from "react";

interface HelpTipProps {
  /**
   * What the mark is asking about, for the accessible name. Not optional: a
   * button whose name is a punctuation mark tells a screen-reader user nothing,
   * and there would be several of these on one page.
   */
  readonly label: string;
  readonly children: React.ReactNode;
  /**
   * "warning" draws a red "!" instead of the "?": something here needs doing,
   * not just explaining. Same button, same panel, same keyboard behaviour --
   * only the mark changes, so it is never a second popover to keep in step.
   */
  readonly tone?: "help" | "warning";
}

/**
 * A question mark beside a feature, which opens a short explanation.
 *
 * This exists to replace a habit rather than to add a decoration. There are
 * roughly 128 lines of ambient muted text across this app explaining what panels
 * are for. Each reads as thoughtful on its own; together they crowd out the
 * figures the panels exist to show. So the rule is: text answering "what is
 * this?" goes behind one of these, and text that changes what you are about to
 * do stays on the page where it will be read before acting.
 *
 * **Click, not hover.** A hover-only explanation never appears on a touch screen
 * and cannot be reached from a keyboard, which is exactly why the 64 `title`
 * attributes already in this codebase are not the answer to the same problem.
 *
 * **The panel is in normal flow, under the button.** A floating panel anchored to
 * the mark would need flip-and-clamp logic that nothing else here has, and would
 * still run off the edge at phone width or inside a scrolling container. Pushing
 * the following row down is the whole cost, and it cannot be positioned wrongly.
 *
 * Escape closes it, handled locally on the wrapper. `Modal` has an Escape stack
 * for stacked dialogs, but it is module-private and this is not a dialog -- it
 * traps no focus and covers nothing, so it needs none of that. `CourseSearch`
 * already handles Escape locally on an anchored panel the same way.
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
