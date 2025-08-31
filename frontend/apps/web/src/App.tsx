import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import Nav from "./components/Nav";
import AdminDashboard from "./pages/AdminDashboard";
import TaskGraph from "./pages/TaskGraph";
import TemplateStudio from "./pages/TemplateStudio";
import PipelineView from "./pages/PipelineView";
import Insights from "./pages/Insights";
import ReportsPage from "./pages/ReportsPage";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Profile from "./pages/Profile";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem("token");
  return token ? (
    <>
      <Nav />
      <Toaster position="top-right" />
      {children}
    </>
  ) : (
    <Navigate to="/login" />
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/profile"
          element={
            <PrivateRoute>
              <Profile />
            </PrivateRoute>
          }
        />
        <Route
          path="/graph"
          element={
            <PrivateRoute>
              <TaskGraph />
            </PrivateRoute>
          }
        />
        <Route
          path="/pipeline"
          element={
            <PrivateRoute>
              <PipelineView />
            </PrivateRoute>
          }
        />
        <Route
          path="/studio"
          element={
            <PrivateRoute>
              <TemplateStudio />
            </PrivateRoute>
          }
        />
        <Route
          path="/insights"
          element={
            <PrivateRoute>
              <Insights />
            </PrivateRoute>
          }
        />
        <Route
          path="/reports"
          element={
            <PrivateRoute>
              <ReportsPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <AdminDashboard />
            </PrivateRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
  // Neue Pipeline-View ist über die Route /pipeline erreichbar
}
