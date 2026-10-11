import { useCallback } from "react";
import { useAuth } from "../../../app/auth/AuthContext";
import SharingSection from "../../../shared/components/SharingSection";
import { cancelEventLink, eventInviteLink, fetchEventSharing, makeEventLink, removeEventMember } from "../sharing";

interface Props {
  readonly eventId: string;
}

/**
 * Sharing one of your own events (Phase 2 item 9b, D24), inside its editor.
 * Whoever joins sees when and where on their own calendar, and can leave.
 * They change nothing of it.
 */
export default function EventSharingSection({ eventId }: Props) {
  const { user } = useAuth();
  const userId = user?.id ?? "";
  const load = useCallback(() => fetchEventSharing(userId, eventId), [userId, eventId]);
  if (!user) return null;
  return (
    <SharingSection
      noun="event"
      load={load}
      makeLink={() => makeEventLink(userId, eventId)}
      cancelLink={() => cancelEventLink(userId, eventId)}
      removeMember={(memberId) => removeEventMember(userId, eventId, memberId)}
      linkFor={eventInviteLink}
      notShareable="Only a one-off event can be shared: not a repeat, a shift, or a block from a grade."
      help={<>
        Anyone who joins through your link sees this event on their own calendar: its title, time, place
        and notes. They can leave it, but change nothing. Never its course. Only you can edit or delete it,
        or change who is on it.
      </>}
    />
  );
}
