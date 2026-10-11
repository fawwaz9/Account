import { useCallback } from "react";
import { useAuth } from "../../../app/auth/AuthContext";
import SharingSection from "../../../shared/components/SharingSection";
import { cancelTaskLink, fetchTaskSharing, makeTaskLink, removeTaskMember, taskInviteLink } from "../sharing";

interface Props {
  readonly taskId: string;
  /** Called after someone is taken off, so the row's "with ..." updates. */
  readonly onChanged?: () => void;
}

/**
 * Sharing one of your own tasks (Phase 2 item 9a, D23), inside its editor.
 *
 * Whoever joins sees the title, notes and due date, can tick it done and edit
 * its text, and can leave. Never its course, grade, timer, priority or tags.
 */
export default function TaskSharingSection({ taskId, onChanged }: Props) {
  const { user } = useAuth();
  const userId = user?.id ?? "";
  const load = useCallback(() => fetchTaskSharing(userId, taskId), [userId, taskId]);
  if (!user) return null;
  return (
    <SharingSection
      noun="task"
      load={load}
      makeLink={() => makeTaskLink(userId, taskId)}
      cancelLink={() => cancelTaskLink(userId, taskId)}
      removeMember={(memberId) => removeTaskMember(userId, taskId, memberId)}
      linkFor={taskInviteLink}
      notShareable="One of a repeat can't be shared. Share a one-off task instead."
      onChanged={onChanged}
      help={<>
        Anyone who joins through your link sees this task&rsquo;s title, notes and due date. They can tick
        it done for everyone and edit its title and notes. Never its course, grade, timer, priority or tags.
        Only you can change its date, delete it, or change who is on it.
      </>}
    />
  );
}
