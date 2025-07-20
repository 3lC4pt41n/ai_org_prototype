// card.jsx – ein extrem simples Card-Wrapper
import React, { HTMLAttributes, PropsWithChildren } from "react";

export function Card({ className = "", children, ...rest }: PropsWithChildren<HTMLAttributes<HTMLDivElement>>) {
  return (
    <div className={`rounded-xl shadow border bg-white ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function CardContent({ className = "", children, ...rest }: PropsWithChildren<HTMLAttributes<HTMLDivElement>>) {
  return (
    <div className={`p-4 ${className}`} {...rest}>
      {children}
    </div>
  );
}
