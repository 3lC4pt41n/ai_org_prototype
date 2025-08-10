import React from "react";

const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL ?? "http://localhost:3000";

export default function Insights() {
  const token = localStorage.getItem("token");
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
    <div className="insights-container" style={{ height: "100%", width: "100%", background: "#1e1e1e" }}>
      <iframe
        src={grafanaSrc}
        style={{ width: "100%", height: "800px", border: "0" }}
        title="AI Org Insights"
      />
    </div>
  );
}
