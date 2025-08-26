import React from "react";

interface FeedbackFormProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export default function FeedbackForm({ value, onChange, onSubmit }: FeedbackFormProps) {
  const disabled = value.trim() === "";
  return (
    <div className="mt-4">
      <label className="block mb-1">Feedback (optional)</label>
      <textarea
        className="w-full border rounded p-2"
        rows={3}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        className="btn btn-secondary mt-2"
        onClick={onSubmit}
        disabled={disabled}
      >
        Feedback senden (optional)
      </button>
    </div>
  );
}
