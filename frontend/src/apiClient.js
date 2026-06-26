const PRODUCTION_FRONTEND_HOSTS = new Set(["deepalpha.best", "www.deepalpha.best"]);
const PRODUCTION_API_BASE = "https://api.deepalpha.best";
const LOCAL_API_BASE = "http://127.0.0.1:8000";


export function resolveApiBase({ envApiBase = "", hostname = "" } = {}) {
  const configured = String(envApiBase || "").trim().replace(/\/+$/, "");
  if (configured) return configured;

  const normalizedHost = String(hostname || "").trim().toLowerCase();
  if (PRODUCTION_FRONTEND_HOSTS.has(normalizedHost)) {
    return PRODUCTION_API_BASE;
  }

  return LOCAL_API_BASE;
}


export const API_BASE = resolveApiBase({
  envApiBase: import.meta.env?.VITE_API_BASE,
  hostname: typeof window === "undefined" ? "" : window.location.hostname,
});

