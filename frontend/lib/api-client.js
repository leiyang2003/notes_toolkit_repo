import { ACTION_TYPES } from "../../packages/contracts/web/index.js";

export { ACTION_TYPES };

export class ApiError extends Error {
  constructor(message, code = "api_error", status = 0) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

function joinUrl(base, path) {
  if (!base) {
    return path;
  }
  return `${base.replace(/\/$/, "")}${path}`;
}

export function createApiClient(backendBaseUrl) {
  async function call(path, init = {}) {
    const response = await fetch(joinUrl(backendBaseUrl, path), {
      credentials: "include",
      cache: "no-store",
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers || {}),
      },
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }

    if (!response.ok) {
      throw new ApiError(
        payload.message || `Request failed with status ${response.status}`,
        payload.code || "request_failed",
        response.status,
      );
    }

    return payload;
  }

  return {
    backendBaseUrl,
    loginUrl(nextUrl) {
      const query = nextUrl ? `?next=${encodeURIComponent(nextUrl)}` : "";
      return joinUrl(backendBaseUrl, `/auth/google/login${query}`);
    },
    getSession() {
      return call("/api/session", { method: "GET" });
    },
    logout() {
      return call("/auth/logout", { method: "POST" });
    },
    getProjects() {
      return call("/api/projects", { method: "GET" });
    },
    initProject(projectName) {
      return call("/api/init", {
        method: "POST",
        body: JSON.stringify({ project_name: projectName }),
      });
    },
    createProject(projectName) {
      return call("/api/projects", {
        method: "POST",
        body: JSON.stringify({ project_name: projectName }),
      });
    },
    getProjectState(projectName) {
      return call(`/api/project/${encodeURIComponent(projectName)}/state`, { method: "GET" });
    },
    runAction(projectName, actionBody) {
      return call(`/api/project/${encodeURIComponent(projectName)}/actions`, {
        method: "POST",
        body: JSON.stringify(actionBody),
      });
    },
  };
}
