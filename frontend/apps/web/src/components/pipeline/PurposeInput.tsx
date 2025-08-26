import React from "react";

interface PurposeInputProps {
  value: string;
  onChange: (value: string) => void;
  onStart: () => void;
}

export default function PurposeInput({ value, onChange, onStart }: PurposeInputProps) {
  return (
    <div className="flex space-x-2">
      <input
        className="flex-grow border rounded px-4 py-2"
        placeholder="Purpose eingeben…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        className="btn btn-primary"
        onClick={onStart}
        disabled={!value.trim()}
      >
        Start
      </button>
    </div>
  );
}
