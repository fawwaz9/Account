import { useEffect, useState } from "react";
import { previewPrerequisites } from "../api";
import { PrerequisitePreview } from "../types";
import { STATUS_WORDS } from "./PrerequisitesPanel";

interface Props {
  readonly userId: string;
  readonly code: string;
  readonly year: number;
  readonly semester: string;
}

const KIND_WORDS = { prerequisite: "prerequisites", corequisite: "co-requisites" } as const;
const WAIT_MS = 400;

/**
 * The prerequisite warning while adding a course (Phase 2 item 7).
 *
 * Only when the shared catalogue has the course and a rule you don't yet meet.
 * Words only: the Add button beside it is never disabled, because exceptions
 * are made (D3). Silent when the read fails or there is nothing to say.
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
