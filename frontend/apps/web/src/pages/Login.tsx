import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { login } from "../../../../packages/api-client/src";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import Logo from "../components/ui/Logo";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e?: React.FormEvent) {
    if (e) {
      e.preventDefault();
    }
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await login({ email: email.trim(), password });
      localStorage.setItem("token", resp?.access_token || "");
      localStorage.setItem("user_email", email.trim());
      navigate("/admin", { replace: true });
    } catch (err: any) {
      setError(err?.message || "Login fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container-app">
      <header style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <Logo size={28} />
        <b>AI Org</b>
      </header>

      <div className="card" style={{ maxWidth: 480, margin: "40px auto" }}>
        <div className="card-header">Anmelden</div>
        <div className="card-body">
          <p className="muted" style={{ marginBottom: 16 }}>
            Melde dich mit deiner E-Mail und deinem Passwort an.
          </p>
          <form onSubmit={handleSubmit}>
            <Input
              label="E-Mail"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <Input
              label="Passwort"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            {error && (
              <div className="danger" style={{ marginBottom: 12 }}>
                {error}
              </div>
            )}
            <Button type="submit" block disabled={loading}>
              {loading ? "Anmelden…" : "Anmelden"}
            </Button>
          </form>
          <div className="muted" style={{ marginTop: 12, fontSize: 14 }}>
            Kein Konto?{' '}
            <Link to="/register" style={{ color: "var(--brand-600)" }}>
              Jetzt registrieren
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

