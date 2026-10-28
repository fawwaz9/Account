import { useCallback } from "react";
import { useAuth } from "../../../app/auth/AuthContext";
import SharingSection from "../../../shared/components/SharingSection";
import { cancelTaskLink, fetchTaskSharing, makeTaskLink, removeTaskMember, taskInviteLink } from "../sharing";

/** The task to share, and a callback for after a member is removed. */
interface Props {
  readonly taskId: string;
  /** Called after a member is removed, so the row's "with ..." label updates. */
  readonly onChanged?: () => void;
}

/**
 * The Share panel in a task's editor. Members see the title, notes and due date, can tick it
 * and edit its text, and can leave; never its course, grade, timer, priority or tags.
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
