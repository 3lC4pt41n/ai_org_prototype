import React from 'react';

interface FeedbackItem {
  version: number;
  text: string;
}

interface FeedbackFormProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onApprove: () => void;
  history: FeedbackItem[];
  disabled?: boolean;
}

export default function FeedbackForm({
  value,
  onChange,
  onSend,
  onApprove,
  history,
  disabled = false,
}: FeedbackFormProps) {
  const canSend = value.trim() !== '' && !disabled;
  return (
    <div className="mt-4">
      <label className="block mb-1">Feedback</label>
      <textarea
        className="w-full border rounded p-2"
        rows={3}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="flex gap-2 mt-2">
        <button className="btn btn-secondary" onClick={onSend} disabled={!canSend}>
          Feedback senden
        </button>
        <button className="btn btn-primary" onClick={onApprove} disabled={disabled}>
          Freigeben
        </button>
      </div>
      {history.length > 0 && (
        <div className="mt-4">
          <h3 className="font-semibold">Verlauf:</h3>
          <ul className="text-sm list-disc ml-5">
            {history.map((h) => (
              <li key={h.version}>
                <b>Version {h.version}:</b> {h.text || '(ohne Text)'}{' '}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
