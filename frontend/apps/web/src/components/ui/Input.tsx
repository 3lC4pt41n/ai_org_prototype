import React from "react";

type Props = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
};

export function Input({ label, hint, ...rest }: Props) {
  return (
    <label style={{ display: "block", marginBottom: 12 }}>
      {label && <div style={{ marginBottom: 6, fontWeight: 600 }}>{label}</div>}
      <input {...rest} />
      {!!hint && (
        <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
          {hint}
        </div>
      )}
    </label>
  );
}

