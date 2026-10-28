import { CSSProperties } from "react";

/** An icon's mask image and an optional extra class. */
interface IconProps {
  /** Imported PNG used as a mask: drawn black on transparent. */
  readonly src: string;
  readonly className?: string;
}

/** Decorative app icon: the image's shape used as a mask and filled with `--gold`. */
export default function Icon({ src, className }: IconProps) {
  return (
    <span
      className={className ? `appIcon ${className}` : "appIcon"}
      style={{ "--icon": `url("${src}")` } as CSSProperties}
      aria-hidden="true"
    />
  );
}
