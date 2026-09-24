/**
 * "Something is on its way and the app is fine."
 *
 * Lifted out of `ProtectedRoute`, which had the only copy, once a second place
 * needed the same thing: the boundary that waits for a route's code to arrive.
 * Two hand-written spinners would drift, and the more obscure of the two --
 * the one shown for a few hundred milliseconds on a slow connection -- is the
 * one that would drift unnoticed.
 *
 * `<output>` rather than a div with `role="status"`: it carries the status role
 * natively, which is what S6819 asks for, and it announces itself to a screen
 * reader without the author having to remember the attribute.
 */
export default function Loading({ label }: { readonly label: string }) {
  return (
    <output className="authBootstrap">
      <span className="authBootstrapSpinner" aria-hidden="true" />
      <span className="small-text muted">{label}</span>
    </output>
  );
}
