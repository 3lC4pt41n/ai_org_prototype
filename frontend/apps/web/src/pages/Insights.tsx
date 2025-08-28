import React, { useState } from "react";

const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL ?? "http://localhost:3000";

export default function Insights() {
  const token = localStorage.getItem("token");
  const [insightsData] = useState<any[]>([]);
  let tenantId = "";
  if (token) {
    try {
      const base64Payload = token.split(".")[1];
      const payload = JSON.parse(atob(base64Payload));
      tenantId = payload.tenant_id;
    } catch (e) {
      console.error("Failed to decode JWT", e);
    }
  }

  const dashboardUID = "AIOrgInsights";
  const grafanaSrc = `${GRAFANA_URL}/d/${dashboardUID}?orgId=1&var-tenant=${tenantId}&kiosk=1`;

  return (
    <div className="min-h-screen p-4">
      <h1 className="text-3xl font-bold mb-4">Insights</h1>
      <p className="mb-4">Datenanalysen und Metriken.</p>
      <iframe
        src={grafanaSrc}
        style={{ width: "100%", height: "800px", border: "0" }}
        title="AI Org Insights"
      />
      {insightsData.length === 0 && (
        <div className="text-red-600 mt-4">Keine Daten verfügbar.</div>
      )}
    </div>
  );
}
