import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import AdminDashboard from './pages/AdminDashboard';
import TaskGraph from './pages/TaskGraph';
import TemplateStudio from './pages/TemplateStudio';
import PipelinePage from './pages/PipelinePage';
import Nav from './components/Nav';
import Login from './pages/Login';
import Register from './pages/Register';
import Insights from './pages/Insights';
import ReportsPage from './pages/ReportsPage';

export default function App() {
  const token = localStorage.getItem('token');
  return (
    <BrowserRouter>
      {token ? (
        <>
          <Nav />
          <Toaster position="top-right" />
          <Routes>
            <Route path="/" element={<AdminDashboard />} />
            <Route path="/graph" element={<TaskGraph />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/studio" element={<TemplateStudio />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="/reports" element={<ReportsPage />} />
          </Routes>
        </>
      ) : (
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="*" element={<Login />} />
        </Routes>
      )}
    </BrowserRouter>
  );
}
