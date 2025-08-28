import React from "react";
import { useNavigate } from "react-router-dom";

export default function Profile() {
  const navigate = useNavigate();
  const token = localStorage.getItem("token") || "";
  let tenantId = "";
  try {
    const base64 = token.split(".")[1];
    const payload = JSON.parse(atob(base64));
    tenantId = payload.tenant_id;
  } catch {}

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/login");
  };

  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-4">Profil</h1>
      <p className="mb-2">
        Angemeldet als <span className="font-mono">{tenantId}</span>
      </p>
      <button
        onClick={handleLogout}
        className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
      >
        Logout
      </button>
    </div>
  );
}
