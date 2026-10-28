import { useEffect, useState } from "react";
import { previewPrerequisites } from "../api";
import { PrerequisitePreview } from "../types";
import { STATUS_WORDS } from "./PrerequisitesPanel";

/** The course being added: its code, school year and term. */
interface Props {
  readonly userId: string;
  readonly code: string;
  readonly year: number;
  readonly semester: string;
}

/** Plural wording for each requisite kind. */
const KIND_WORDS = { prerequisite: "prerequisites", corequisite: "co-requisites" } as const;
/** Typing pause, in ms, before the catalogue is asked. */
const WAIT_MS = 400;

/**
 * While adding a course, the catalogue requisites not yet met; words only, never blocking the add.
 * Asks after a typing pause once the code has 6+ characters; silent on failure.
 */
export default function PrerequisiteWarning({ userId, code, year, semester }: Props) {
  const [preview, setPreview] = useState<PrerequisitePreview | null>(null);

  useEffect(() => {
    setPreview(null);
    if (code.trim().length < 6) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      previewPrerequisites(userId, code.trim(), year, semester)
        .then((found) => { if (!cancelled) setPreview(found); })
        .catch(() => { if (!cancelled) setPreview(null); });
    }, WAIT_MS);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [userId, code, year, semester]);

  const unmet = (preview?.kinds ?? []).filter((k) => k.shared && k.shared.result.status !== "met");
  if (!preview?.catalogue || unmet.length === 0) return null;

  const name = `${preview.catalogue.subject} ${preview.catalogue.number}`;
  return (
    <div className="prereqWarning" role="status">
      {unmet.map((k) => (
        <p key={k.kind} className="small-text">
          {name}&rsquo;s {KIND_WORDS[k.kind]}: {k.shared!.text}. {STATUS_WORDS[k.shared!.result.status]}.
        </p>
      ))}
      <p className="small-text muted">You can still add it.</p>
    </div>
  );
}
