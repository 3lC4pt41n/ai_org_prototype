import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { register, login } from '@api';

export default function Register() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = name.trim().length >= 2 && /\S+@\S+\.\S+/.test(email) && password.length >= 8;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || loading) return;
    setLoading(true);
    setError(null);
    try {
      // 1) Try to register -> backend may return access_token directly
      const resp = await register({
        name: name.trim(),
        email: email.trim(),
        password,
      });
      let token = resp?.access_token;
      // 2) If no token was returned, perform a login using the provided credentials
      if (!token) {
        const loginResp = await login({ email: email.trim(), password });
        token = loginResp.access_token;
      }
      if (!token) throw new Error('Registrierung erfolgreich, aber kein Token erhalten.');
      localStorage.setItem('token', token);
      localStorage.setItem('user_email', email.trim());
      localStorage.setItem('user_name', name.trim());
      // optional: flag onboarding as done
      localStorage.setItem('skipOnboarding', 'true');
      // Go to Admin Dashboard (adjust route if needed)
      navigate('/admin', { replace: true });
    } catch (err: any) {
      setError(typeof err === 'string' ? err : err?.message || 'Registrierung fehlgeschlagen.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-slate-900 rounded-2xl shadow-xl p-6 border border-slate-800">
        <h1 className="text-2xl font-semibold mb-2">Create your account</h1>
        <p className="text-slate-400 mb-6 text-sm">
          Registriere dich mit Name, E‑Mail und Passwort. Du erhältst sofortigen Zugang.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="name" className="block text-sm mb-1 text-slate-300">
              Name
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jane Doe"
              className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-500"
              autoComplete="name"
              required
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm mb-1 text-slate-300">
              E‑Mail
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jane@example.com"
              className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 outline-none focus:ring-2 focus:ring-emerald-500"
              autoComplete="email"
              required
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm mb-1 text-slate-300">
              Passwort
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mind. 8 Zeichen"
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 pr-10 outline-none focus:ring-2 focus:ring-emerald-500"
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                onClick={() => setShowPw((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 text-xs"
                aria-label={showPw ? 'Passwort verbergen' : 'Passwort anzeigen'}
              >
                {showPw ? 'Hide' : 'Show'}
              </button>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Verwende ein starkes Passwort (mindestens 8 Zeichen).
            </p>
          </div>

          {error && (
            <div className="text-red-400 text-sm border border-red-800 bg-red-950/30 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={!canSubmit || loading}
            className={`w-full rounded-lg px-4 py-2 font-medium transition ${
              !canSubmit || loading
                ? 'bg-slate-700 text-slate-400 cursor-not-allowed'
                : 'bg-emerald-600 hover:bg-emerald-700 text-white'
            }`}
          >
            {loading ? 'Registriere…' : 'Registrieren'}
          </button>
        </form>

        <div className="mt-6 text-sm text-slate-400">
          Bereits ein Konto?{' '}
          <Link to="/login" className="text-emerald-400 hover:text-emerald-300 underline">
            Anmelden
          </Link>
        </div>
      </div>
    </div>
  );
}
