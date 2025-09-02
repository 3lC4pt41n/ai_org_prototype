import React from "react";
import usePipelineStore from "../store/pipelineStore";

export default function PurposeSelector() {
  const { purposes, selectedPurposeId, setSelectedPurpose, pausePurpose, startPurpose } =
    usePipelineStore();

  return (
    <div className="mb-4">
      <label className="mr-2 font-semibold">Zweck auswählen:</label>
      <select
        className="border rounded px-2 py-1"
        value={selectedPurposeId || ""}
        onChange={(e) => setSelectedPurpose(e.target.value)}
      >
        <option value="" disabled>
          -- Zweck wählen --
        </option>
        {purposes.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      {selectedPurposeId && (
        <div className="mt-2 space-x-2">
          <button
            className="px-3 py-1 bg-red-500 text-white rounded"
            onClick={() => pausePurpose(selectedPurposeId)}
          >
            Pause Zweck
          </button>
          <button
            className="px-3 py-1 bg-green-500 text-white rounded"
            onClick={() => startPurpose(selectedPurposeId)}
          >
            Start Zweck
          </button>
        </div>
      )}
    </div>
  );
}
