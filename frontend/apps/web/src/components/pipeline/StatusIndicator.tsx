import React from "react";

interface StatusIndicatorProps {
  status: "idle" | "loading" | "ready" | "complete";
}

export default function StatusIndicator({ status }: StatusIndicatorProps) {
  let text = "";
  let color = "";
  if (status === "idle") {
    text = "Bereit";
    color = "text-gray-600";
  } else if (status === "loading") {
    text = "Wird ausgeführt...";
    color = "text-blue-600";
  } else if (status === "ready") {
    text = "Feedback ausstehend";
    color = "text-yellow-600";
  } else if (status === "complete") {
    text = "Fertig";
    color = "text-green-600";
  }
  return <h3 className={`text-lg font-medium ${color}`}>{text}</h3>;
}
