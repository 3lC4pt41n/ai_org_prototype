// src/pages/AdminDashboard.jsx
import React, { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Gauge, History } from "lucide-react";

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

  useEffect(() => {
    const controller = new AbortController();

    const tick = () =>
      Promise.all([getJson("/"), getJson("/backlog")])
        .then(([s, b]) => {
          setBudget(s.budget_left);
          setBacklog(b);
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
    </div>
  );
}
