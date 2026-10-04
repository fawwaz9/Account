import { EventKind, EVENT_KIND_LABELS, EXAM_KINDS } from "../types";
import { DEFAULT_KIND_COLORS, KindColors, kindColor, kindStyle } from "../kindColors";

interface EventColorsProps {
  readonly colors: KindColors;
  readonly onChange: (next: KindColors) => void;
}

const KINDS = Object.keys(EVENT_KIND_LABELS) as EventKind[];

/**
 * A colour per event kind, each beside a chip drawn exactly as the calendar
 * will draw it -- the same classes, so an exam still shows its heavier bar.
 *
 * Only changed kinds are kept. "Default" removes the kind rather than storing
 * the default's value, so if a default is ever retuned, kinds nobody touched
 * follow it instead of keeping a stale copy. It needs no confirmation: it loses
 * one colour and is one click to redo.
 */
export default function EventColors({ colors, onChange }: EventColorsProps) {
  function set(kind: EventKind, color: string) {
    onChange({ ...colors, [kind]: color.toLowerCase() });
  }

  function reset(kind: EventKind) {
    const next = { ...colors };
    delete next[kind];
    onChange(next);
  }

  return (
    <ul className="kindColorList">
      {KINDS.map((kind) => {
        const id = `kind-color-${kind}`;
        const changed = colors[kind] !== undefined && colors[kind] !== DEFAULT_KIND_COLORS[kind];
        return (
          <li key={kind} className="kindColorRow">
            <label htmlFor={id}>{EVENT_KIND_LABELS[kind]}</label>
            <input
              id={id}
              type="color"
              className="kindColorInput"
              value={kindColor(kind, colors)}
              onChange={(event) => set(kind, event.target.value)}
            />
            {/* Decoration: the label already names the kind. */}
            <span
              className={`calChip calChip-${kind}${EXAM_KINDS.includes(kind) ? " calChipExam" : ""} kindColorSample`}
              style={kindStyle(kind, colors)}
              aria-hidden="true"
            >
              <span className="calChipTitle">{EVENT_KIND_LABELS[kind]}</span>
            </span>
            {changed && (
              <button
                type="button"
                className="courseLinkAdd"
                onClick={() => reset(kind)}
                aria-label={`Use the default colour for ${EVENT_KIND_LABELS[kind]}`}
              >
                Default
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
