type ValidationIssue = { loc?: unknown[]; msg?: unknown };
type ApiError = {
  code?: unknown;
  message?: unknown;
  response?: {
    status?: unknown;
    data?: {
      detail?: unknown;
      message?: unknown;
    };
  };
};

export function apiErrorMessage(error: unknown, fallback = "The request could not be completed. Please try again.") {
  const value = error as ApiError | null;
  const data = value?.response?.data;
  const detail = data?.detail ?? data?.message;

  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((issue) => {
      if (typeof issue === "string") return issue;
      const item = issue as ValidationIssue;
      const location = Array.isArray(item.loc) ? item.loc.slice(1).map(String).join(".") : "";
      const message = typeof item.msg === "string" ? item.msg : "Invalid value";
      return location ? location + ": " + message : message;
    }).filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  if (!value?.response && (value?.code === "ECONNABORTED" || value?.code === "ETIMEDOUT")) {
    return "The server took too long to respond. Try again, and contact your administrator if this keeps happening.";
  }
  if (!value?.response && (value?.code === "ERR_NETWORK" || value?.message === "Network Error")) {
    return "The server could not be reached. Check your connection and try again.";
  }
  if (typeof value?.message === "string" && value.message.trim() && !/^Request failed with status code \d+$/.test(value.message)) {
    return value.message;
  }
  if (typeof value?.response?.status === "number") {
    if (value.response.status === 429) return "Too many requests were sent. Wait a moment and try again.";
    if (value.response.status >= 500) return "The server encountered a problem. Try again, or contact your administrator if it continues.";
    if (value.response.status === 404) return "The requested item could not be found. Refresh the page and try again.";
  }
  return fallback;
}
