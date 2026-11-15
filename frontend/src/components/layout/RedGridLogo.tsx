export function RedGridLogo({ className = "size-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <circle cx="16" cy="16" r="14" className="fill-mars" />
      <g className="stroke-mars-foreground" strokeWidth="1.25" fill="none" opacity="0.85">
        <path d="M2.5 11h27M2.5 21h27M11 2.5v27M21 2.5v27" />
      </g>
      <circle cx="21" cy="11" r="2.4" className="fill-sand" />
    </svg>
  );
}
