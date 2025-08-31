import React from "react";
import usePipelineStore from "../store/pipelineStore";

export default function ArtifactList() {
  const { artifacts, selectArtifact } = usePipelineStore();
  return (
    <div className="border rounded p-2 mt-4">
      <h2 className="font-semibold mb-2">Artefakte</h2>
      {artifacts.length === 0 ? (
        <p className="text-gray-500">Keine Artefakte verfügbar.</p>
      ) : (
        <ul className="space-y-1">
          {artifacts.map((art) => (
            <li key={art.id}>
              <button
                className="text-blue-500 underline"
                onClick={() => selectArtifact(art.id)}
              >
                {art.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
