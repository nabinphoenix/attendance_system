import axios from "axios";
import { apiErrorMessage } from "@/lib/apiErrorMessage";
import { notifySystemFeedback } from "@/lib/systemFeedback";
// Default to the same origin so a phone can use the Next.js proxy instead of
// trying to reach its own localhost:8000.
const api = axios.create({ baseURL: process.env.NEXT_PUBLIC_API_URL || "", withCredentials: true });

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/admin")) {
    const collegeId = sessionStorage.getItem("platform_college_id");
    if (collegeId && !config.headers["X-College-ID"]) config.headers["X-College-ID"] = collegeId;
  }
  return config;
});

let redirectingToLogin = false;

function failureTitle(status: number | undefined, requestUrl: string, description: string) {
  if (requestUrl.includes("/google-workspace/")) {
    if (/oauth is not configured/i.test(description)) return "Google Workspace setup is incomplete";
    if (/no google workspace account is connected|connection has expired or been revoked|reconnect it/i.test(description)) {
      return "Google account connection needs attention";
    }
    if (/connect a verified @/i.test(description)) return "Use the approved Google Workspace account";
    if (status === 502 || status === 504 || /could not contact google workspace|did not respond before/i.test(description)) {
      return "Google Workspace could not be reached";
    }
    if (status === 403 || /google denied this request|permissions?/i.test(description)) return "Google permissions need attention";
    if (status === 404) return "Google file or resource was not found";
    if (!status) return "Google Workspace could not be reached";
    return "Google Workspace request failed";
  }
  if (requestUrl.includes("/routine/pending")) return "Pending combined sections could not be loaded";
  if (status === 409) return "This action conflicts with existing data";
  if (status === 422) return "Please correct the submitted information";
  if (status === 403) return "You do not have permission to do this";
  if (status === 404) return "The requested item was not found";
  if (status === 429) return "Too many requests";
  if (status && status >= 500) return "The server could not complete this request";
  if (!status) return "Cannot reach the server";
  return "Request could not be completed";
}

api.interceptors.response.use(
  (response) => {
    const method = String(response.config.method ?? "get").toLowerCase();
    const requestUrl = String(response.config.url ?? "").split("?")[0].toLowerCase();
    const isMutation = ["post", "put", "patch", "delete"].includes(method);
    const isAuthFlow = requestUrl.includes("/auth/");
    const isPreviewOrCheck = /\/(availability|preview|validate)(\/|$)/.test(requestUrl);

    if (isMutation && !isAuthFlow && !isPreviewOrCheck) {
      const data = response.data as { success_count?: number; failed_count?: number } | undefined;
      if (requestUrl.includes("/import") && typeof data?.success_count === "number") {
        const failed = data.failed_count ?? 0;
        notifySystemFeedback({
          tone: failed ? "warning" : "success",
          title: failed ? "Import completed with issues" : "Import completed",
          description: String(data.success_count) + " row(s) imported; " + String(failed) + " failed. Review the row outcomes for details.",
        });
      } else if (method === "delete") {
        notifySystemFeedback({ tone: "success", title: "Deletion complete", description: "The selected item was deleted successfully." });
      } else if (method === "put" || method === "patch") {
        notifySystemFeedback({ tone: "success", title: "Changes saved", description: "Your changes were saved successfully." });
      } else {
        notifySystemFeedback({ tone: "success", title: "Action completed", description: "The requested action completed successfully." });
      }
    }
    return response;
  },
  (error) => {
    const status = error.response?.status;
    const requestUrl = String(error.config?.url ?? "").split("?")[0].toLowerCase();
    const isAuthFlow = requestUrl.includes("/auth/");
    const isLoginRequest = requestUrl.includes("/api/v1/auth/login");
    const hasDedicatedRoutineToast = /\/api\/v1\/academic\/sections\/\d+\/routine\/(preview|import)$/.test(requestUrl);

    if (!isAuthFlow && status !== 401 && !hasDedicatedRoutineToast && error.code !== "ERR_CANCELED") {
      const description = apiErrorMessage(error, "The request could not be completed. Please try again.");
      notifySystemFeedback({
        tone: "danger",
        title: failureTitle(status, requestUrl, description),
        description,
      });
    }

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
