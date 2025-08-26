import React from "react";

interface StatusIndicatorProps {
  status: "idle" | "loading" | "ready" | "complete";
}

export default function StatusIndicator({ status }: StatusIndicatorProps) {
  if (status === "idle") return null;

  const steps = [
    { key: "loading", label: "Warte auf PRD", color: "bg-gray-400" },
    { key: "ready", label: "Feedback ausstehend", color: "bg-blue-600" },
    { key: "complete", label: "Erledigt", color: "bg-green-600" }
  ];

  const currentIndex =
    status === "loading" ? 0 : status === "ready" ? 1 : status === "complete" ? 2 : 0;

  return (
    <ol className="flex items-center space-x-4 text-sm">
      {steps.map((step, index) => (
        <li key={step.key} className="flex items-center space-x-2">
          <span
            className={`w-3 h-3 rounded-full ${index < currentIndex ? "bg-green-600" : index === currentIndex ? step.color : "bg-gray-300"}`}
          ></span>
          <span>{step.label}</span>
        </li>
      ))}
    </ol>
  );
}
