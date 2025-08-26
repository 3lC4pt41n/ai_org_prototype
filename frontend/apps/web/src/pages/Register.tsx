import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { register, login } from "../../../../packages/api-client/src";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import Logo from "../components/ui/Logo";

export default function Register() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canSubmit =
    name.trim().length >= 2 && /\S+@\S+\.\S+/.test(email) && password.length >= 8;

  async function handleSubmit(e?: React.FormEvent) {
    if (e) {
      e.preventDefault();
    }
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await register({ name: name.trim(), email: email.trim(), password });
      const token = resp?.access_token ?? (await login({ email, password }))?.access_token;
      localStorage.setItem("token", token || "");
      navigate("/admin", { replace: true });
    } catch (err: any) {
      setError(err?.message || "Registrierung fehlgeschlagen.");
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
      <div className="card" style={{ maxWidth: 520, margin: "40px auto" }}>
        <div className="card-header">Create your account</div>
        <div className="card-body">
          <p className="muted" style={{ marginBottom: 16 }}>
            Registriere dich mit Name, E-Mail und Passwort. Du erhältst sofortigen Zugang.
          </p>
          <form onSubmit={handleSubmit}>
            <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} required />
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
              hint="Mindestens 8 Zeichen"
            />
            {error && (
              <div className="danger" style={{ marginBottom: 12 }}>
                {error}
              </div>
            )}
            <Button type="submit" block disabled={!canSubmit || loading}>
              {loading ? "Registriere…" : "Registrieren"}
            </Button>
          </form>
          <div className="muted" style={{ marginTop: 12, fontSize: 14 }}>
            Bereits ein Konto?{' '}
            <Link to="/login" style={{ color: "var(--brand-600)" }}>
              Anmelden
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

