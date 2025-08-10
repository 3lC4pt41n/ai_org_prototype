import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import AdminDashboard from "./pages/AdminDashboard";
import TaskGraph from "./pages/TaskGraph";
import TemplateStudio from "./pages/TemplateStudio";
import PipelineDashboard from "./pages/PipelineDashboard";
import Nav from "./components/Nav";
import Login from "./pages/Login";
import Insights from "./pages/Insights";
import ReportsPage from "./pages/ReportsPage";

export default function App() {
  const token = localStorage.getItem("token");
  return (
    <BrowserRouter>
      {token ? (
        <>
          <Nav />
          <Toaster position="top-right" />
          <Routes>
            <Route path="/" element={<AdminDashboard />} />
            <Route path="/graph" element={<TaskGraph />} />
            <Route path="/pipeline" element={<PipelineDashboard />} />
            <Route path="/studio" element={<TemplateStudio />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="/reports" element={<ReportsPage />} />
          </Routes>
        </>
      ) : (
        <Routes>
          <Route path="*" element={<Login />} />
        </Routes>
      )}
    </BrowserRouter>
  );
}
