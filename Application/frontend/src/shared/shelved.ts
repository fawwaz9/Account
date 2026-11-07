/**
 * The shelf, mirroring the backend's app/shared/shelved.py: the Fitness page with
 * its teams, clubs, activity, boards, directory, gym buddy and correlations is
 * kept in the code but reachable from nowhere, and its API answers 404.
 * Shelved 2026-11-07, by the owner. Set this to false, and take the names out of
 * the backend's SHELVED, to bring it back.
 */
export const FITNESS_SHELVED = true;

/** Shown when an old team or club link is opened while the shelf is closed. */
export const SHELVED_INVITE = "Teams and clubs aren't available right now, so this link can't be opened.";
