import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { login } from '@api';

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = /\S+@\S+\.\S+/.test(email) && password.length >= 8;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || loading) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await login({ email: email.trim(), password });
      localStorage.setItem('token', resp.access_token);
      localStorage.setItem('user_email', email.trim());
      navigate('/admin', { replace: true });
    } catch (err: any) {
      setError(typeof err === 'string' ? err : err?.message || 'Login fehlgeschlagen.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-slate-900 rounded-2xl shadow-xl p-6 border border-slate-800">
        <h1 className="text-2xl font-semibold mb-2">Login</h1>
        <p className="text-slate-400 mb-6 text-sm">
          Melde dich mit deiner E‑Mail und deinem Passwort an.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
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
                placeholder="Passwort"
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 pr-10 outline-none focus:ring-2 focus:ring-emerald-500"
                autoComplete="current-password"
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
            {loading ? 'Lade…' : 'Anmelden'}
          </button>
        </form>

        <div className="mt-6 text-sm text-slate-400">
          Kein Konto?{' '}
          <Link to="/register" className="text-emerald-400 hover:text-emerald-300 underline">
            Jetzt registrieren
          </Link>
        </div>
      </div>
    </div>
  );
}
