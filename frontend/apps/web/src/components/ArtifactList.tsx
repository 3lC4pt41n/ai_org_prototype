import React from "react";

interface Artifact {
  name: string;
  url: string;
}

const ArtifactList: React.FC<{ artifacts: Artifact[] }> = ({ artifacts }) => {
  const downloadArtifact = (a: Artifact) => {
    const token = localStorage.getItem("token");
    fetch(a.url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
      .then((res) => {
        if (!res.ok) throw new Error("Download fehlgeschlagen");
        return res.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = a.name;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
      })
      .catch((err) => console.error("Download error", err));
  };
  return (
    <div className="artifact-list">
      <h3 className="mb-2 font-semibold">Artefakte</h3>
      {artifacts.length === 0 ? (
        <p className="text-sm text-gray-500">Keine Artefakte vorhanden.</p>
      ) : (
        <ul>
          {artifacts.map((a, i) => (
            <li key={i}>
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  downloadArtifact(a);
                }}
                className="text-blue-600 underline"
              >
                {a.name}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default ArtifactList;
