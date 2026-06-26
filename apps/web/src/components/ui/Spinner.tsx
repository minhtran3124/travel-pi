export interface SpinnerProps {
  label?: string;
  className?: string;
}

export function Spinner({ label = "Loading", className }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label={label}
      className={[
        "inline-block size-4 animate-spin rounded-pill border-2 border-line border-t-coral-bright",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="sr-only">{label}</span>
    </span>
  );
}
