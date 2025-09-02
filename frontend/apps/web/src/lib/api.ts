import axios from "axios";

// Base URL for all API requests. Falls back to '/api' if not provided.
export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

const api = axios.create({
  baseURL: API_BASE,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
