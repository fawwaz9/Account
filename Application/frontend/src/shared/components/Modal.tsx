import { useEffect, useId, useRef } from "react";

/** Mounted dialogs, innermost last; only the top one answers Escape and Tab. */
const stack: symbol[] = [];

/** Selector for the elements that can take focus inside a dialog. */
const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/** A dialog's title, close handler, body and optional extra panel class. */
interface ModalProps {
  /** Dialog heading; `aria-labelledby` points at it. */
  readonly title: React.ReactNode;
  readonly onClose: () => void;
  readonly children: React.ReactNode;
  /** Extra class on the panel, for the few dialogs that need more width. */
  readonly panelClassName?: string;
}

/**
 * Shared dialog shell: traps focus, closes on Escape and hands focus back on close.
 * Never closes on a backdrop click, so a stray click cannot discard a part-filled form.
 */
export default function Modal({ title, onClose, children, panelClassName }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  // Where focus sat before the dialog opened, so it can be handed back. Without
  // this, closing drops focus to the top of the document and a keyboard user
  // loses their place on the page entirely.
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;

    const panel = panelRef.current;
    if (panel) {
      // A form dialog opens on its first field, which is genuinely useful. A
      // confirm dialog's first control is the destructive button, so there focus
      // goes to the panel instead -- the title gets announced and the user has to
      // tab to the action deliberately.
      const firstField = panel.querySelector<HTMLElement>(
        "input:not([disabled]):not([type='hidden']), select:not([disabled]), textarea:not([disabled])"
      );
      (firstField ?? panel).focus();
    }

    return () => {
      previouslyFocused.current?.focus?.();
    };
  }, []);

  // Identity for this dialog's place in the stack. A ref so it survives re-renders.
  const token = useRef<symbol>(undefined as unknown as symbol);
  token.current ??= Symbol("dialog");

  useEffect(() => {
    const self = token.current;
    stack.push(self);
    return () => {
      const at = stack.lastIndexOf(self);
      if (at !== -1) stack.splice(at, 1);
    };
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      // Only the innermost dialog reacts; the ones underneath stay put.
      if (stack[stack.length - 1] !== token.current) return;

      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;

      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        // offsetParent is null for anything display:none, so a control in a
        // collapsed branch of the form is not a tab stop.
        (element) => element.offsetParent !== null
      );
      if (focusable.length === 0) {
        // Nothing to land on, so keep focus on the panel rather than letting Tab
        // walk into the page behind the overlay.
        event.preventDefault();
        panel.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      // Tab past the last control, or Shift+Tab before the first, wraps inside
      // the dialog. Focus sitting on the panel itself counts as "before the
      // first", so the first Tab enters the dialog rather than leaving it.
      if (event.shiftKey && (active === first || active === panel)) {
        event.preventDefault();
        last.focus();
      } else if ((!event.shiftKey && active === last) || !panel.contains(active)) {
        // Past the last control, or focus has drifted out of the dialog
        // altogether: either way, land on the first control.
        event.preventDefault();
        first.focus();
      }
    }

    // On the document rather than the panel: focus can briefly sit outside the
    // dialog (right after mount, or if a control unmounts under it), and Escape
    // has to work in those moments too.
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="popup">
      <div
        ref={panelRef}
        className={panelClassName ? `addCoursePopup ${panelClassName}` : "addCoursePopup"}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </div>
  );
}
