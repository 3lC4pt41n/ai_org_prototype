import { Link } from "react-router-dom";
import { useEffect } from "react";
import { Moon, Sun } from "lucide-react";
import useThemeStore from "../store/themeStore";

export default function Nav() {
  const theme = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const fetchTheme = useThemeStore((state) => state.fetchTheme);

  useEffect(() => {
    fetchTheme();
  }, [fetchTheme]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <nav className="p-2 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 flex items-center gap-4 border-b dark:border-slate-700">
      <Link to="/" className="hover:underline">Dashboard</Link>
      <Link to="/graph" className="hover:underline">Graph</Link>
      <Link to="/pipeline" className="hover:underline">Pipeline</Link>
      <Link to="/studio" className="hover:underline">Studio</Link>
      <Link to="/insights" className="hover:underline">Insights</Link>
      <Link to="/reports" className="hover:underline">Reports</Link>
      <Link to="/profile" className="hover:underline">Profil</Link>
      <button
        onClick={toggleTheme}
        className="ml-auto p-2 rounded-full hover:bg-gray-100 dark:hover:bg-slate-700"
      >
        {theme === "dark" ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
      </button>
    </nav>
  );
}
