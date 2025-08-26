import React from "react";

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "outline";
  block?: boolean;
};

export function Button({ variant = "primary", block = false, className = "", ...rest }: Props) {
  const base = "btn " + (block ? "w-full " : "");
  const style = variant === "primary" ? "btn-primary" : "btn-outline";
  return <button {...rest} className={`${base} ${style} ${className}`} />;
}

