import React, { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const genericErrorMessage =
    "Login fehlgeschlagen – bitte E‑Mail/Passwort prüfen oder später erneut versuchen.";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username: email, password }),
      });
      if (!res.ok) {
        if (import.meta.env.DEV) {
          const contentType = res.headers.get("content-type") ?? "";
          try {
            if (contentType.includes("application/json")) {
              const errorJson = await res.json();
              console.error(
                "Login-Fehlerantwort:",
                JSON.stringify(errorJson) || `${res.status} ${res.statusText}`,
              );
            } else {
              const errorText = await res.text();
              console.error(
                "Login-Fehlerantwort:",
                errorText || `${res.status} ${res.statusText}`,
              );
            }
          } catch (parseError) {
            console.error("Login-Fehlerantwort konnte nicht gelesen werden:", parseError);
          }
        }
        setError(genericErrorMessage);
        return;
      }
      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      navigate("/");
    } catch (err) {
      if (import.meta.env.DEV) {
        console.error("Login-Request fehlgeschlagen:", err);
      }
      setError(genericErrorMessage);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-sm w-full">
        <h1 className="text-2xl font-bold mb-4">Login</h1>
        {error && <div className="text-red-500 mb-2">{error}</div>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="email"
            placeholder="E-Mail"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full p-2 border rounded"
            required
          />
          <input
            type="password"
            placeholder="Passwort"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full p-2 border rounded"
            required
          />
          <button
            type="submit"
            className="w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Anmelden
          </button>
        </form>
      </div>
    </div>
  );
}
