/** Spinner with a label in an `output` element, which screen readers announce as a status. */
export default function Loading({ label }: { readonly label: string }) {
  return (
    <output className="authBootstrap">
      <span className="authBootstrapSpinner" aria-hidden="true" />
      <span className="small-text muted">{label}</span>
    </output>
  );
}
