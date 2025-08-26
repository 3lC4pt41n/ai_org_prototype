import React from "react";
/**
 * Minimalistisches Logo: vernetzte Knoten (Agenten) + Akzentlinie.
 * CI: Anthrazit (#2F3035) + Akzent (#0ABAF0).
 */
export default function Logo({ size = 28 }: { size?: number }) {
  const s = size;
  return (
    <svg width={s} height={s} viewBox="0 0 48 48" fill="none" aria-label="AI Org">
      <circle cx="10" cy="24" r="5" stroke="#2F3035" strokeWidth="2" />
      <circle cx="38" cy="14" r="5" stroke="#2F3035" strokeWidth="2" />
      <circle cx="38" cy="34" r="5" stroke="#2F3035" strokeWidth="2" />
      <path d="M15 24 L33 16" stroke="#0ABAF0" strokeWidth="2" />
      <path d="M15 24 L33 32" stroke="#2F3035" strokeWidth="2" opacity=".8" />
    </svg>
  );
}

