import { useCallback } from "react";
import { useAuth } from "../../../app/auth/AuthContext";
import SharingSection from "../../../shared/components/SharingSection";
import { cancelEventLink, eventInviteLink, fetchEventSharing, makeEventLink, removeEventMember } from "../sharing";

/** The event to share. */
interface Props {
  readonly eventId: string;
}

/** The Share panel in an event's editor; members see it on their calendar but change nothing. */
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
