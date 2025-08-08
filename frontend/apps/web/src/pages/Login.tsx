import { useState } from "react";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const resp = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password })
    });
    if (resp.ok) {
      const data = await resp.json();
      localStorage.setItem("token", data.access_token);
      location.href = "/";
    } else {
      setError("Login failed");
    }
  };

  return (
    <div className="p-4 flex justify-center">
      <form onSubmit={submit} className="space-y-2 w-64">
        {error && <p className="text-red-500">{error}</p>}
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email"
          className="w-full p-2 border"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="password"
          className="w-full p-2 border"
        />
        <button type="submit" className="w-full bg-blue-600 text-white p-2">
          Login
        </button>
      </form>
    </div>
  );
}
