import React from "react";

interface Artifact {
  name: string;
  url: string;
}

const ArtifactList: React.FC<{ artifacts: Artifact[] }> = ({ artifacts }) => (
  <div className="artifact-list">
    <h3 className="mb-2 font-semibold">Artefakte</h3>
    {artifacts.length === 0 ? (
      <p className="text-sm text-gray-500">Keine Artefakte vorhanden.</p>
    ) : (
      <ul>
        {artifacts.map((a, i) => (
          <li key={i}>
            <a href={a.url} className="text-blue-600 underline">
              {a.name}
            </a>
          </li>
        ))}
      </ul>
    )}
  </div>
);

export default ArtifactList;
