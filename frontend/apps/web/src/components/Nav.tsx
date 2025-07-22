import { Link } from 'react-router-dom'

export default function Nav() {
  return (
    <nav className="p-2 bg-slate-800 text-white flex gap-4">
      <Link to="/" className="hover:underline">Dashboard</Link>
      <Link to="/graph" className="hover:underline">Graph</Link>
      <Link to="/studio" className="hover:underline">Studio</Link>
    </nav>
  )
}
