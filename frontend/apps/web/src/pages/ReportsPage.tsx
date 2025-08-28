import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "/api";

export default function ReportsPage() {
  const [artifacts, setArtifacts] = useState<any[]>([]);
  useEffect(() => {
    const token = localStorage.getItem("token");
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    fetch(`${API}/artifacts`, { headers })
      .then((res) => res.json())
      .then((data) => setArtifacts(data))
      .catch(() => {});
  }, []);
  return (
    <div className="min-h-screen p-4">
      <h1 className="text-3xl font-bold mb-4">Reports</h1>
      <p className="mb-4">Berichte zum Projekt.</p>
      <div className="bg-white shadow rounded-sm">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-100">
            <tr>
              <th className="px-4 py-2 text-left font-medium text-gray-600">Report</th>
              <th className="px-4 py-2 text-left font-medium text-gray-600">Created</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {artifacts.map((art) => (
              <tr key={art.id}>
                <td className="px-4 py-2">{art.name}</td>
                <td className="px-4 py-2">
                  {new Date(art.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-2">
                  <a
                    href={`/artifact/${art.id}`}
                    className="text-emerald-600 hover:underline"
                  >
                    Download
                  </a>
                </td>
              </tr>
            ))}
            {artifacts.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-2 text-red-400">
                  Keine Berichte generiert.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
