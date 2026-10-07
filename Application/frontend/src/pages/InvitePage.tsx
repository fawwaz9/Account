import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../app/auth/AuthContext";
import { acceptInvite, previewInvite } from "../features/partners/api";
import { AcceptStatus } from "../features/partners/types";

const REFUSED: Record<Exclude<AcceptStatus, "accepted">, string> = {
  invalid: "That invite link has expired, been used, or been cancelled. Ask for a new one.",
  own: "That's your own invite link. Send it to the person you want as a partner.",
  already: "You're already partners.",
};

/**
 * Opening an invite link (Phase 2 item 10, D16). The token is in the fragment
 * (/invite#token), so it never reaches a server log; it is sent to the API in
 * a request body. Shows who sent it, then asks before anything happens.
 */
export default function InvitePage() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const token = decodeURIComponent(location.hash.replace(/^#/, ""));
  const [inviter, setInviter] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!user) return;
    if (token.length < 16) {
      setProblem(REFUSED.invalid);
      return;
    }
    let cancelled = false;
    previewInvite(user.id, token)
      .then((found) => { if (!cancelled) setInviter(found.inviter_name); })
      .catch(() => { if (!cancelled) setProblem(REFUSED.invalid); });
    return () => { cancelled = true; };
  }, [user, token]);

  async function accept() {
    if (!user) return;
    setBusy(true);
    try {
      const { status } = await acceptInvite(user.id, token);
      if (status === "accepted") {
        navigate("/tasks", { replace: true });
        return;
      }
      setProblem(REFUSED[status]);
    } catch {
      setProblem("That didn't work. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container invitePage">
      <h1 className="title">An invite</h1>
      {problem ? (
        <p>{problem} <Link to="/tasks">Go to your tasks</Link></p>
      ) : inviter ? (
        <>
          <p>
            <strong>{inviter}</strong> would like you as an accountability partner. You&rsquo;d each see the
            share of the week&rsquo;s tasks the other has done, and their run of good weeks. Never task names,
            grades or money. Either of you can end it at any time.
          </p>
          <div className="catalogueActions">
            <button type="button" className="calButton calButtonPrimary" onClick={() => void accept()} disabled={busy}>
              Become partners
            </button>
            <Link to="/tasks" className="calButton">No thanks</Link>
          </div>
        </>
      ) : (
        <p className="muted" role="status">Checking the invite…</p>
      )}
    </div>
  );
}
