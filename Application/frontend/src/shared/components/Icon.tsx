import { CSSProperties } from "react";

interface IconProps {
  /** An imported image whose shape is drawn: black on transparent. */
  readonly src: string;
  readonly className?: string;
}

/**
 * One of the app's icons, always in gold.
 *
 * The PNG is a mask, not an image: only its shape is used, and the stylesheet
 * fills it with `--gold`. So the files can stay as drawn (black on
 * transparent), every icon matches the rest of the app's gold, and changing
 * that colour is one token. Decorative: whatever it sits in carries the name.
 */
export default function Icon({ src, className }: IconProps) {
  return (
    <span
      className={className ? `appIcon ${className}` : "appIcon"}
      style={{ "--icon": `url("${src}")` } as CSSProperties}
      aria-hidden="true"
    />
  );
}
