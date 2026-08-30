import axios from "axios";
// Default to the same origin so a phone can use the Next.js proxy instead of
// trying to reach its own localhost:8000.
const api = axios.create({ baseURL: process.env.NEXT_PUBLIC_API_URL || "", withCredentials: true });

let redirectingToLogin = false;

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const requestUrl = String(error.config?.url ?? "");
    const isLoginRequest = requestUrl.includes("/api/v1/auth/login");

    // A 401 means the session cookie is missing or has expired. Redirect once
    // so individual pages never show a misleading "Not authenticated" error.
    if (
      status === 401
      && !isLoginRequest
      && typeof window !== "undefined"
      && window.location.pathname !== "/login"
      && !redirectingToLogin
    ) {
      redirectingToLogin = true;
      window.location.replace("/login");
    }

    return Promise.reject(error);
  },
);

export default api;
