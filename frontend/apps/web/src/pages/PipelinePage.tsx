import React, { useState } from 'react';
import AImarChatPanel from '../components/AImarChatPanel';

const STEPS = ['Zweck', 'PRD', 'Architektur', 'Plan', 'Bericht'];

export default function PipelinePage() {
  const [activeStep, setActiveStep] = useState(STEPS[0]);

  return (
    <div className="flex h-screen">
      <aside className="w-60 bg-gradient-to-b from-indigo-50 to-violet-50 border-r flex flex-col">
        <h2 className="px-4 py-3 text-sm font-semibold text-slate-700">Pipeline</h2>
        <nav className="flex-1">
          {STEPS.map((step) => (
            <button
              key={step}
              onClick={() => setActiveStep(step)}
              className={`w-full text-left px-4 py-2 text-sm rounded-md my-0.5 transition ${
                activeStep === step
                  ? 'bg-gradient-to-r from-indigo-500 to-violet-500 text-white shadow-sm'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {step}
            </button>
          ))}
        </nav>
      </aside>

      <main className="flex-1 flex flex-col bg-gradient-to-br from-white to-slate-50">
        <header className="border-b px-6 py-3 flex items-center justify-between bg-white/70 backdrop-blur-md">
          <h1 className="text-lg font-semibold text-slate-800">{activeStep}</h1>
          <div className="flex items-center gap-2">
            <button className="px-3 py-1 text-xs rounded-md bg-slate-200 hover:bg-slate-300 transition">
              Pause Zweck
            </button>
            <button className="px-3 py-1 text-xs rounded-md bg-gradient-to-r from-green-500 to-emerald-600 text-white shadow hover:opacity-90 transition">
              Start Zweck
            </button>
            <button className="px-3 py-1 text-xs rounded-md bg-slate-200 hover:bg-slate-300 transition">
              Modus
            </button>
          </div>
        </header>

        <div className="flex flex-1 overflow-hidden">
          <section className="flex-1 p-6 overflow-y-auto">
            <div className="prose max-w-none">
              <h2 className="text-xl font-semibold text-slate-800">{activeStep} Dokument</h2>
              <p className="text-sm text-slate-500">
                Hinweis: Sie betrachten evtl. eine ältere Version
              </p>
              <div className="mt-4 border rounded-xl p-5 bg-white/80 backdrop-blur shadow-md">
                <p className="text-slate-700">
                  Hier werden die Inhalte des Schritts <b>{activeStep}</b> angezeigt (z. B. Markdown
                  vom Artefakt).
                </p>
              </div>
            </div>
            <div className="mt-6 border-t pt-4">
              <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <input type="checkbox" className="rounded border-slate-300" />
                Freigabe erteilt
              </label>
              <p className="text-xs text-slate-500 mt-1">Datum: __.__.20__</p>
            </div>
          </section>

          <aside className="w-96 border-l flex flex-col bg-white/70 backdrop-blur">
            <div className="p-4 border-b">
              <h3 className="text-sm font-semibold text-slate-800">Kontext & Metadaten</h3>
              <ul className="text-xs text-slate-600 mt-2 list-disc pl-4 space-y-1">
                <li>Chat Kontext: {activeStep}</li>
                <li>Offene Punkte: Restore-Funktion fehlt</li>
                <li>Letzte Änderung: v1.1 am 12.09.2025</li>
              </ul>
            </div>
            <div className="flex-1 flex flex-col">
              <AImarChatPanel purposeId="demo-purpose" paused={false} />
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
