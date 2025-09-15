import React from 'react';
import { toast } from 'react-hot-toast';
import usePipelineStore from '../store/pipelineStore';

export default function PurposeSelector() {
  const {
    purposes,
    selectedPurposeId,
    setSelectedPurpose,
    pausePurpose,
    startPurpose,
    updatePurposeMode,
  } = usePipelineStore();

  const currentPurpose = purposes.find((p) => p.id === selectedPurposeId) ?? null;

  const handleModeChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
    const newMode = event.target.value as 'manual' | 'auto';
    if (!selectedPurposeId || currentPurpose?.mode === newMode) {
      return;
    }
    try {
      await updatePurposeMode(selectedPurposeId, newMode);
      toast.success(
        `Modus auf "${newMode === 'auto' ? 'Automatisch' : 'Manuell'}" gesetzt.`,
      );
    } catch {
      toast.error('Modusänderung fehlgeschlagen.');
    }
  };

  return (
    <div className="mb-4 flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <label className="font-semibold text-sm sm:text-base">Zweck auswählen:</label>
        <select
          className="border rounded px-2 py-1 text-sm"
          value={selectedPurposeId || ''}
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
      </div>
      {selectedPurposeId && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            className="px-3 py-1 bg-red-500 text-white rounded text-sm"
            onClick={() => pausePurpose(selectedPurposeId)}
          >
            Pause Zweck
          </button>
          <button
            className="px-3 py-1 bg-green-500 text-white rounded text-sm"
            onClick={() => startPurpose(selectedPurposeId)}
          >
            Start Zweck
          </button>
          <label className="text-sm font-medium">Modus:</label>
          <select
            className="border rounded-md text-sm px-2 py-1"
            value={currentPurpose?.mode ?? 'manual'}
            onChange={handleModeChange}
          >
            <option value="manual">Manuell</option>
            <option value="auto">Automatisch</option>
          </select>
        </div>
      )}
    </div>
  );
}
