import React, { useState } from "react";
import usePipelineStore from "../store/pipelineStore";

export default function ArtifactContent() {
  const { selectedArtifactId, artifactContent, feedbacks, postFeedback, updateArtifact } =
    usePipelineStore();
  const [newFeedback, setNewFeedback] = useState("");
  if (!selectedArtifactId) {
    return null;
  }
  return (
    <div className="border rounded p-2 mt-4">
      <h2 className="font-semibold mb-2">Artefakt-Inhalt (ID: {selectedArtifactId})</h2>
      <textarea
        className="w-full border rounded p-2 mb-2"
        rows={10}
        value={artifactContent}
        onChange={(e) => updateArtifact(selectedArtifactId, e.target.value)}
      />
      <button
        className="mb-4 px-3 py-1 bg-blue-500 text-white rounded"
        onClick={() => {
          if (selectedArtifactId) {
            updateArtifact(selectedArtifactId, artifactContent);
          }
        }}
      >
        Speichern
      </button>
      <h3 className="font-semibold">Feedback</h3>
      {feedbacks.map((fb) => (
        <div key={fb.id} className="border rounded p-2 mb-2">
          <p>{fb.content}</p>
          <p className="text-xs text-gray-500">
            von {fb.user} am {fb.timestamp ? new Date(fb.timestamp).toLocaleString() : '—'}
          </p>
        </div>
      ))}
      <textarea
        className="w-full border rounded p-2"
        rows={3}
        value={newFeedback}
        onChange={(e) => setNewFeedback(e.target.value)}
        placeholder="Feedback hinzufügen..."
      />
      <button
        className="mt-2 px-3 py-1 bg-green-500 text-white rounded"
        onClick={() => {
          if (selectedArtifactId && newFeedback.trim()) {
            postFeedback(selectedArtifactId, newFeedback);
            setNewFeedback("");
          }
        }}
      >
        Feedback senden
      </button>
    </div>
  );
}
