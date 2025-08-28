import React from "react";

interface PurposeInputProps {
  value: string;
  onChange: (newVal: string) => void;
  onStart: () => void;
}

export default function PurposeInput({ value, onChange, onStart }: PurposeInputProps) {
  const canStart = value.trim() !== "";
  return (
    <div className="mt-4">
      <label className="block mb-1">Neues Projektziel</label>
      <input
        className="w-full border rounded p-2"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Projektziel eingeben..."
      />
      <button className="btn btn-primary mt-2" onClick={onStart} disabled={!canStart}>
        Start
      </button>
    </div>
  );
}
