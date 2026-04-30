"use client";

import { useEffect, useMemo, useState } from "react";
import LoginScreen from "./login-screen";
import ToastStack from "./toast-stack";
import WorkspaceScreen, { mapAiEditAction, mapEditAction } from "./workspace-screen";
import { DialogModal } from "./dialog-modal";
import { ACTION_TYPES, ApiError, createApiClient } from "../lib/api-client";
import { loadRuntimeConfig } from "../lib/runtime-config";

const EMPTY_STATE = {
  notes: [],
  todos: [],
  potentials: [],
  done: [],
  notes_count: 0,
  todo_count: 0,
  potential_pending_count: 0,
  updated_at: "",
};

const PREVIEW_STATE = {
  notes: [
    { id: 1, section: "Changes Made", text: "Aligned dashboard cards with stronger visual hierarchy and faster scan patterns." },
    { id: 2, section: "Focus Today", text: "Validate desktop and mobile UI before shipping the refactor." },
  ],
  todos: [
    { id: 1, text: "Finalize responsive spacing for action rows" },
    { id: 2, text: "Review error handling text in toasts" },
  ],
  potentials: [
    { id: 1, status: "pending", text: "Add keyboard shortcuts for quick todo triage" },
    { id: 2, status: "promoted", text: "Introduce project-level quick filters" },
  ],
  done: [{ timestamp: "2026-04-24 12:00", text: "Migrated frontend to fully componentized Next.js" }],
  notes_count: 2,
  todo_count: 2,
  potential_pending_count: 1,
  updated_at: "2026-04-24 14:00 CST",
};

function nextToastId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function focusById(id) {
  if (typeof window === "undefined") {
    return;
  }
  const element = document.getElementById(id);
  if (element) {
    element.focus();
  }
}

function isTypingTarget(target) {
  if (!target) {
    return false;
  }
  const tag = String(target.tagName || "").toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || Boolean(target.isContentEditable);
}

function stripSystemPrefixes(text) {
  let raw = String(text || "").trim();
  raw = raw.replace(/^\s*-\s*\[[ xX]\]\s*/, "").trim();
  while (true) {
    const next = raw.replace(/^\s*\[\d{4}-\d{2}-\d{2}[^\]]*\]\s*/, "").replace(/^\s*\[LT\]\s*/i, "").trim();
    if (next === raw) {
      break;
    }
    raw = next;
  }
  return raw;
}

export default function DashboardApp({ initialProjectName = "" }) {
  const [backendBaseUrl, setBackendBaseUrl] = useState("");
  const [session, setSession] = useState({ ok: true, logged_in: false, email: "" });
  const [projects, setProjects] = useState([]);
  const [activeProject, setActiveProject] = useState(initialProjectName);
  const [state, setState] = useState(EMPTY_STATE);
  const [isBooting, setIsBooting] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [isQaMobileViewport, setIsQaMobileViewport] = useState(false);
  const [isPreviewWorkspace, setIsPreviewWorkspace] = useState(false);
  const [viewFilter, setViewFilter] = useState("all");
  const [noteQuery, setNoteQuery] = useState("");
  const [todoQuery, setTodoQuery] = useState("");
  const [potentialQuery, setPotentialQuery] = useState("");
  const [activeActionKey, setActiveActionKey] = useState("");
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [aiDialog, setAiDialog] = useState({
    open: false,
    kind: "note",
    id: null,
    originalText: "",
    instruction: "",
    suggestion: "",
    step: "instruction",
    loading: false,
  });

  const client = useMemo(() => createApiClient(backendBaseUrl), [backendBaseUrl]);

  function pushToast(kind, title, message) {
    const id = nextToastId();
    setToasts((prev) => [...prev, { id, kind, title, message }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, 5000);
  }

  async function ensureProjects(apiClient) {
    const projectPayload = await apiClient.getProjects();
    const nextProjects = Array.isArray(projectPayload.projects) ? projectPayload.projects : [];

    if (nextProjects.length === 0) {
      const initResponse = await apiClient.initProject("home");
      const initializedProject = initResponse.project || "home";
      return [
        {
          project: initializedProject,
          todo_count: initResponse.state?.todo_count || 0,
          potential_pending_count: initResponse.state?.potential_pending_count || 0,
          last_activity: initResponse.state?.updated_at || "",
        },
      ];
    }

    return nextProjects;
  }

  async function refreshState(projectName, { silent = false } = {}) {
    if (!projectName || isPreviewWorkspace) {
      return;
    }
    if (!silent) {
      setIsRefreshing(true);
    }
    try {
      const response = await client.getProjectState(projectName);
      setState(response);
    } catch (error) {
      pushToast("error", "Refresh failed", error.message || "Could not refresh project state.");
    } finally {
      if (!silent) {
        setIsRefreshing(false);
      }
    }
  }

  async function refreshProjectsList() {
    const payload = await client.getProjects();
    const nextProjects = Array.isArray(payload.projects) ? payload.projects : [];
    setProjects(nextProjects);
    return nextProjects;
  }

  async function bootstrap() {
    setIsBooting(true);
    try {
      const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
      const previewMode = params?.get("preview") === "workspace";
      setIsPreviewWorkspace(previewMode);

      if (previewMode) {
        setSession({ ok: true, logged_in: true, email: "preview@notes-toolkit.local" });
        setProjects([{ project: "preview-home", todo_count: 2, potential_pending_count: 1, last_activity: PREVIEW_STATE.updated_at }]);
        setActiveProject("preview-home");
        setState(PREVIEW_STATE);
        return;
      }

      const runtime = await loadRuntimeConfig();
      setBackendBaseUrl(runtime.backendBaseUrl || "");

      const freshClient = createApiClient(runtime.backendBaseUrl || "");
      const sessionPayload = await freshClient.getSession();
      setSession(sessionPayload);

      if (!sessionPayload.logged_in) {
        setProjects([]);
        setActiveProject("");
        setState(EMPTY_STATE);
        return;
      }

      const projectRows = await ensureProjects(freshClient);
      setProjects(projectRows);
      const preferredProject = initialProjectName || activeProject || projectRows[0]?.project || "";
      setActiveProject(preferredProject);

      if (preferredProject) {
        const nextState = await freshClient.getProjectState(preferredProject);
        setState(nextState);
      }
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Failed to bootstrap workspace.";
      pushToast("error", "Startup failed", message);
    } finally {
      setIsBooting(false);
    }
  }

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      setIsQaMobileViewport(params.get("viewport") === "mobile");
    }
    bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialProjectName]);

  useEffect(() => {
    if (!session.logged_in) {
      return undefined;
    }

    const onKeyDown = (event) => {
      if (isTypingTarget(event.target)) {
        return;
      }

      const key = String(event.key || "").toLowerCase();
      if (key === "n") {
        event.preventDefault();
        focusById("new-note");
      }
      if (key === "t") {
        event.preventDefault();
        focusById("new-todo");
      }
      if (key === "r") {
        event.preventDefault();
        if (activeProject && !isPreviewWorkspace) {
          refreshState(activeProject);
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [session.logged_in, activeProject, isPreviewWorkspace]);

  async function runAction(action, payload = {}) {
    if (!activeProject) {
      return null;
    }
    if (isPreviewWorkspace) {
      pushToast("info", "Preview mode", "Action is disabled in preview mode.");
      return null;
    }

    setIsRefreshing(true);
    try {
      const response = await client.runAction(activeProject, { action, actor: "web", ...payload });
      if (response.state) {
        setState(response.state);
      } else {
        await refreshState(activeProject, { silent: true });
      }
      if (response.message) {
        pushToast("success", "Updated", response.message);
      }
      return response;
    } catch (error) {
      pushToast("error", "Action failed", error.message || "Unable to complete action.");
      return null;
    } finally {
      setIsRefreshing(false);
    }
  }

  async function runActionWithLoading(actionKey, action, payload = {}) {
    setActiveActionKey(actionKey);
    try {
      return await runAction(action, payload);
    } finally {
      setActiveActionKey("");
    }
  }

  function openAiEditDialog(kind, id) {
    setAiDialog({ open: true, kind, id, originalText: "", instruction: "", suggestion: "", step: "instruction", loading: false });
  }

  function closeAiEditDialog() {
    setAiDialog({ open: false, kind: "note", id: null, originalText: "", instruction: "", suggestion: "", step: "instruction", loading: false });
  }

  async function submitAiInstruction(event) {
    event.preventDefault();
    const instruction = String(aiDialog.instruction || "").trim();
    if (!instruction || aiDialog.id === null) {
      return;
    }

    setAiDialog((prev) => ({ ...prev, loading: true }));
    const suggestion = await runAction(mapAiEditAction(aiDialog.kind), { id: aiDialog.id, instruction });
    if (!suggestion?.edited_text) {
      setAiDialog((prev) => ({ ...prev, loading: false }));
      return;
    }

    setAiDialog((prev) => ({
      ...prev,
      loading: false,
      originalText: stripSystemPrefixes(String(suggestion.original_text || "")),
      suggestion: stripSystemPrefixes(String(suggestion.edited_text || "")),
      step: "preview",
    }));
  }

  async function applyAiSuggestion() {
    if (!aiDialog.suggestion || aiDialog.id === null) {
      return;
    }
    setAiDialog((prev) => ({ ...prev, loading: true }));
    await runAction(mapEditAction(aiDialog.kind), { id: aiDialog.id, text: aiDialog.suggestion });
    closeAiEditDialog();
  }

  function login() {
    const loginUrl = client.loginUrl(window.location.href);
    window.location.href = loginUrl;
  }

  async function logout() {
    try {
      await client.logout();
    } finally {
      setSession({ ok: true, logged_in: false, email: "" });
      setProjects([]);
      setState(EMPTY_STATE);
      setActiveProject("");
      pushToast("info", "Signed out", "Your local session has ended.");
    }
  }

  async function handleProjectChange(projectName) {
    setActiveProject(projectName);
    if (!isPreviewWorkspace) {
      await refreshState(projectName);
    }
    if (typeof window !== "undefined") {
      window.history.replaceState({}, "", `/project/${encodeURIComponent(projectName)}`);
    }
  }

  async function handleCreateProject() {
    if (isPreviewWorkspace) {
      pushToast("info", "Preview mode", "Creation is disabled in preview mode.");
      return;
    }
    const normalized = newProjectName.trim();
    if (!normalized) {
      pushToast("error", "Invalid name", "Project name is required.");
      return;
    }

    setIsRefreshing(true);
    try {
      const created = await client.createProject(normalized);
      const nextProjects = await refreshProjectsList();
      const targetProject = created.project || normalized;
      setIsCreatingProject(false);
      setNewProjectName("");
      setActiveProject(targetProject);

      if (created.state) {
        setState(created.state);
      } else {
        await refreshState(targetProject, { silent: true });
      }

      if (typeof window !== "undefined") {
        window.history.replaceState({}, "", `/project/${encodeURIComponent(targetProject)}`);
      }
      pushToast("success", "Project created", `Switched to ${targetProject}.`);

      if (!nextProjects.some((item) => item.project === targetProject)) {
        await refreshProjectsList();
      }
    } catch (error) {
      pushToast("error", "Create project failed", error.message || "Unable to create project.");
    } finally {
      setIsRefreshing(false);
    }
  }

  function handleStartCreateProject() {
    if (isPreviewWorkspace) {
      pushToast("info", "Preview mode", "Creation is disabled in preview mode.");
      return;
    }
    setIsCreatingProject(true);
  }

  function handleCancelCreateProject() {
    setIsCreatingProject(false);
    setNewProjectName("");
  }

  async function handleManualRefresh() {
    if (!activeProject) {
      return;
    }
    if (isPreviewWorkspace) {
      pushToast("info", "Preview mode", "Preview data is static.");
      return;
    }
    await refreshState(activeProject);
  }

  if (isBooting) {
    return (
      <main className="loading-screen">
        <div className="loading-card">
          <p className="eyebrow">Loading</p>
          <h1>Preparing your workspace...</h1>
        </div>
      </main>
    );
  }

  return (
    <div className={isQaMobileViewport ? "qa-mobile" : ""}>
      {!session.logged_in ? (
        <LoginScreen onLogin={login} backendBaseUrl={backendBaseUrl} />
      ) : (
        <WorkspaceScreen
          session={session}
          projects={projects}
          activeProject={activeProject}
          state={state}
          isRefreshing={isRefreshing}
          viewFilter={viewFilter}
          noteQuery={noteQuery}
          todoQuery={todoQuery}
          potentialQuery={potentialQuery}
          onViewFilterChange={setViewFilter}
          onNoteQueryChange={setNoteQuery}
          onTodoQueryChange={setTodoQuery}
          onPotentialQueryChange={setPotentialQuery}
          onQuickAddNote={() => focusById("new-note")}
          onQuickAddTodo={() => focusById("new-todo")}
          onProjectChange={handleProjectChange}
          onStartCreateProject={handleStartCreateProject}
          onCreateProject={handleCreateProject}
          onCancelCreateProject={handleCancelCreateProject}
          isCreatingProject={isCreatingProject}
          newProjectName={newProjectName}
          onNewProjectNameChange={setNewProjectName}
          onRefresh={handleManualRefresh}
          onLogout={logout}
          onAddNote={async (event) => {
            event.preventDefault();
            const formEl = event.currentTarget;
            const form = new FormData(formEl);
            const text = String(form.get("text") || "").trim();
            if (!text) {
              return;
            }
            const result = await runAction(ACTION_TYPES.ADD_NOTE, { text });
            if (result) {
              formEl.reset();
            }
          }}
          onAddTodo={async (event) => {
            event.preventDefault();
            const formEl = event.currentTarget;
            const form = new FormData(formEl);
            const text = String(form.get("text") || "").trim();
            if (!text) {
              return;
            }
            const result = await runAction(ACTION_TYPES.ADD_TODO, { text });
            if (result) {
              formEl.reset();
            }
          }}
          onEditNote={(id, text) => runAction(ACTION_TYPES.EDIT_NOTE, { id, text })}
          onDismissNote={(id) => runActionWithLoading(`dismiss-note-${id}`, ACTION_TYPES.DISMISS_NOTE, { id })}
          onCompleteTodo={(id) => runActionWithLoading(`complete-todo-${id}`, ACTION_TYPES.COMPLETE_TODO, { id })}
          onTodoLongTerm={(id) => runActionWithLoading(`mark-lt-${id}`, ACTION_TYPES.MARK_LONG_TERM_TODO, { id })}
          onTodoShortTerm={(id) => runActionWithLoading(`mark-st-${id}`, ACTION_TYPES.MARK_SHORT_TERM_TODO, { id })}
          onEditTodo={(id, text) => runAction(ACTION_TYPES.EDIT_TODO, { id, text })}
          onApprovePotential={(id) => runActionWithLoading(`approve-potential-${id}`, ACTION_TYPES.APPROVE_POTENTIAL, { id })}
          onRejectPotential={(id) => runActionWithLoading(`reject-potential-${id}`, ACTION_TYPES.REJECT_POTENTIAL, { id })}
          onAiEdit={openAiEditDialog}
          activeActionKey={activeActionKey}
        />
      )}

      <DialogModal
        open={aiDialog.open}
        title={aiDialog.step === "instruction" ? "AI rewrite" : "Apply AI suggestion"}
        actions={
          aiDialog.step === "instruction" ? (
            <>
              <button className="btn" type="button" onClick={closeAiEditDialog} disabled={aiDialog.loading}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                type="submit"
                form="ai-instruction-form"
                disabled={aiDialog.loading || !String(aiDialog.instruction || "").trim()}
              >
                {aiDialog.loading ? "Generating..." : "Generate"}
              </button>
            </>
          ) : (
            <>
              <button className="btn" type="button" onClick={closeAiEditDialog} disabled={aiDialog.loading}>
                Cancel
              </button>
              <button className="btn btn-primary" type="button" onClick={applyAiSuggestion} disabled={aiDialog.loading}>
                {aiDialog.loading ? "Applying..." : "Apply"}
              </button>
            </>
          )
        }
      >
        {aiDialog.step === "instruction" ? (
          <form id="ai-instruction-form" className="dialog-form" onSubmit={submitAiInstruction}>
            <label htmlFor="ai-instruction">Describe how to rewrite this entry</label>
            <textarea
              id="ai-instruction"
              rows={4}
              value={aiDialog.instruction}
              onChange={(event) => setAiDialog((prev) => ({ ...prev, instruction: event.target.value }))}
              autoFocus
            />
          </form>
        ) : (
          <div className="dialog-form">
            <label htmlFor="ai-original">Original</label>
            <textarea id="ai-original" rows={4} value={aiDialog.originalText} readOnly />
            <label htmlFor="ai-suggestion">AI suggestion</label>
            <textarea
              id="ai-suggestion"
              rows={8}
              value={aiDialog.suggestion}
              onChange={(event) => setAiDialog((prev) => ({ ...prev, suggestion: event.target.value }))}
            />
          </div>
        )}
      </DialogModal>

      <ToastStack toasts={toasts} onDismiss={(id) => setToasts((prev) => prev.filter((item) => item.id !== id))} />
    </div>
  );
}
