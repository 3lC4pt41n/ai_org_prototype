// src/pages/AdminDashboard.jsx
import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@ui/Card";
import { Gauge, History, Target, PlayCircle, FileText, Package } from "lucide-react";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function getJson(path) {
  const r = await fetch(`${API}${path}`, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export default function AdminDashboard() {
  const [budget, setBudget] = useState(null);
  const [backlog, setBacklog] = useState([]);
  const [err, setErr] = useState(null);
  const [purposeInput, setPurposeInput] = useState("");
  const [purposeError, setPurposeError] = useState<string | null>(null);
  const [blueprint, setBlueprint] = useState("");
  const [artifacts, setArtifacts] = useState<any[]>([]);

  useEffect(() => {
    const controller = new AbortController();

    const tick = () =>
      Promise.all([getJson("/"), getJson("/backlog"), getJson("/api/artifacts")])
        .then(([s, b, a]) => {
          setBudget(s.budget_left);
          setBacklog(b);
          setArtifacts(a);
          setErr(null);
        })
        .catch((e) => setErr(e.message));

    tick();
    const id = setInterval(tick, 5000);
    return () => {
      clearInterval(id);
      controller.abort();
    };
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetch(`${API}/api/purpose`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ purpose: purposeInput })
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Failed to start");
        }
        return data;
      })
      .then((data) => {
        setBlueprint(data.blueprint || "");
        setPurposeError(null);
        setPurposeInput("");
        // Refresh backlog and artifacts after seeding new tasks
        getJson("/backlog")
          .then((b) => setBacklog(b))
          .catch(() => {});
        getJson("/api/artifacts")
          .then((a) => setArtifacts(a))
          .catch(() => {});
      })
      .catch((e) => setPurposeError(e.message));
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4">
      <Card className="bg-slate-900 text-white">
        <CardContent className="flex items-center gap-2 p-6">
          <Gauge className="text-emerald-400" />
          <div>
            <p className="text-sm">Budget left (USD)</p>
            <p className="text-2xl font-bold">{budget ?? "…"}</p>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-slate-900 text-white col-span-2 max-h-64 overflow-auto">
        <CardContent className="p-4">
          <h2 className="flex items-center gap-2 text-lg mb-2">
            <History /> Backlog
          </h2>
          {err && <p className="text-red-400">{err}</p>}
          <ul className="space-y-1 text-sm">
            {backlog.map((t) => (
              <li key={t.id} className="border-b border-slate-700 py-1">
                <span className="text-amber-400 font-mono mr-2">{t.id}</span>
                {t.description}
              </li>
            ))}
            {backlog.length === 0 && !err && (
              <li className="italic">Queue is empty 🎉</li>
            )}
          </ul>
        </CardContent>
      </Card>

      <Card className="bg-slate-900 text-white col-span-3">
        <CardContent className="p-4">
          <h2 className="flex items-center gap-2 text-lg mb-2">
            <Target /> Define Purpose
          </h2>
          {purposeError && <p className="text-red-400 mb-2">{purposeError}</p>}
          <form onSubmit={handleSubmit} className="flex items-center gap-2">
            <input
              type="text"
              value={purposeInput}
              onChange={(e) => setPurposeInput(e.target.value)}
              placeholder="Enter project purpose..."
              className="flex-1 p-2 rounded bg-slate-800 text-white border border-slate-700"
            />
            <button
              type="submit"
              className="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 flex items-center gap-1"
            >
              <PlayCircle className="w-4 h-4" /> Start
            </button>
          </form>
        </CardContent>
      </Card>

      {blueprint && (
        <Card className="bg-slate-900 text-white col-span-3">
          <CardContent className="p-4">
            <h2 className="flex items-center gap-2 text-lg mb-2">
              <FileText /> Architecture Blueprint
            </h2>
            <pre className="text-sm whitespace-pre-wrap">{blueprint}</pre>
          </CardContent>
        </Card>
      )}

      <Card className="bg-slate-900 text-white col-span-3 max-h-64 overflow-auto">
        <CardContent className="p-4">
          <h2 className="flex items-center gap-2 text-lg mb-2">
            <Package /> Artifacts
          </h2>
          <ul className="space-y-1 text-sm">
            {artifacts.map((a) => (
              <li key={a.id} className="border-b border-slate-700 py-1">
                <span className="text-amber-400 font-mono mr-2">{a.task_id}</span>
                <a
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-amber-400 hover:underline"
                >
                  {a.repo_path.replace(/^demo\//, "")}
                </a>{" "}
                <span className="text-slate-400 text-xs">
                  ({a.media_type}, {new Date(a.created_at).toLocaleString()})
                </span>
              </li>
            ))}
            {artifacts.length === 0 && !err && (
              <li className="italic">No artifacts yet</li>
            )}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
