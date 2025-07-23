import { BrowserRouter, Route, Routes } from "react-router-dom";
import AdminDashboard from "./pages/AdminDashboard";
import TaskGraph from "./pages/TaskGraph";
import TemplateStudio from "./pages/TemplateStudio";
import Nav from "./components/Nav";

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/" element={<AdminDashboard />} />
        <Route path="/graph" element={<TaskGraph />} />
        <Route path="/studio" element={<TemplateStudio />} />
      </Routes>
    </BrowserRouter>
  );
}
