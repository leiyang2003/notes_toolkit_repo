import { useState } from "react";
import { ACTION_TYPES } from "../lib/api-client";
import { DialogModal } from "./dialog-modal";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "notes", label: "Notes" },
  { key: "todos", label: "Todos" },
  { key: "potentials", label: "Potentials" },
  { key: "done", label: "Completed" },
];

function SectionCard({ title, count = null, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <h3>{title}</h3>
        {count !== null ? <span className="panel-count">{count}</span> : null}
      </div>
      {children}
    </section>
  );
}

function RowActions({ children }) {
  return <div className="row-actions">{children}</div>;
}

function ActionButton({ className = "", children, ...props }) {
  return (
    <button className={`btn btn-ghost ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}

function ItemText({ text }) {
  return <p className="item-text">{text}</p>;
}

function ItemMeta({ id, timestamp = "", extra = null }) {
  return (
    <p className="item-meta">
      <span className="id-chip">#{id}</span>
      <span>{timestamp || "-"}</span>
      {extra}
    </p>
  );
}

function EmptyState({ text }) {
  return <p className="empty-state">{text}</p>;
}

function statusClass(status) {
  if (status === "pending") {
    return "status status-pending";
  }
  if (status === "promoted") {
    return "status status-promoted";
  }
  if (status === "rejected") {
    return "status status-rejected";
  }
  return "status";
}

function Metric({ label, value }) {
  return (
    <article className="metric-card">
      <p>{label}</p>
      <strong>{value}</strong>
    </article>
  );
}

function FilterChip({ active, label, onClick }) {
  return (
    <button className={`filter-chip ${active ? "active" : ""}`} onClick={onClick}>
      {label}
    </button>
  );
}

function includesText(value, query) {
  if (!query.trim()) {
    return true;
  }
  return String(value || "")
    .toLowerCase()
    .includes(query.trim().toLowerCase());
}

function stripMetadataPrefixes(text) {
  let raw = String(text || "").trim();
  const todoPrefix = /^\s*-\s*\[[ xX]\]\s*/;
  const timestampPrefix = /^\s*\[\d{4}-\d{2}-\d{2}[^\]]*\]\s*/;
  const longTermPrefix = /^\s*\[LT\]\s*/i;

  raw = raw.replace(todoPrefix, "").trim();
  while (true) {
    const next = raw.replace(longTermPrefix, "").replace(timestampPrefix, "").trim();
    if (next === raw) {
      break;
    }
    raw = next;
  }
  return raw;
}

function extractInlineTimestamp(text) {
  const raw = String(text || "");
  const matched = raw.match(/\[(\d{4}-\d{2}-\d{2}[^[]*?)\]/);
  return matched ? matched[1].trim() : "";
}

function editableContent(text) {
  return stripMetadataPrefixes(text);
}

function displayBody(text) {
  return stripMetadataPrefixes(text);
}

export default function WorkspaceScreen({
  session,
  projects,
  activeProject,
  state,
  isRefreshing,
  viewFilter,
  noteQuery,
  todoQuery,
  potentialQuery,
  onViewFilterChange,
  onNoteQueryChange,
  onTodoQueryChange,
  onPotentialQueryChange,
  onQuickAddNote,
  onQuickAddTodo,
  onProjectChange,
  onStartCreateProject,
  onCreateProject,
  onCancelCreateProject,
  isCreatingProject,
  isCreatingProjectSubmitting,
  newProjectName,
  onNewProjectNameChange,
  onRefresh,
  onLogout,
  onAddNote,
  onAddTodo,
  onEditNote,
  onDismissNote,
  onCompleteTodo,
  onTodoLongTerm,
  onTodoShortTerm,
  onEditTodo,
  onApprovePotential,
  onRejectPotential,
  onAiEdit,
  activeActionKey = "",
}) {
  const [editDialog, setEditDialog] = useState({ open: false, kind: "note", id: null, text: "" });
  const [showReviewedPotentials, setShowReviewedPotentials] = useState(false);
  const [showCompletedItems, setShowCompletedItems] = useState(true);

  const filteredNotes = (state.notes || []).filter(
    (note) => includesText(note.text, noteQuery) || includesText(note.section, noteQuery),
  );
  const filteredTodos = (state.todos || []).filter((todo) => includesText(todo.text, todoQuery));
  const longTermTodoIds = new Set((state.long_term_todos || []).map((todo) => Number(todo.id)));
  const shortTermTodos = filteredTodos.filter((todo) => !longTermTodoIds.has(Number(todo.id)));
  const longTermTodos = filteredTodos.filter((todo) => longTermTodoIds.has(Number(todo.id)));
  const filteredPotentials = (state.potentials || []).filter((item) => includesText(item.text, potentialQuery));
  const pendingPotentials = filteredPotentials.filter((item) => item.status === "pending");
  const reviewedPotentials = filteredPotentials.filter((item) => item.status !== "pending");
  const hasVisiblePotentials =
    pendingPotentials.length > 0 || (showReviewedPotentials && reviewedPotentials.length > 0);

  const showNotes = viewFilter === "all" || viewFilter === "notes";
  const showTodos = viewFilter === "all" || viewFilter === "todos";
  const showPotentials = viewFilter === "all" || viewFilter === "potentials";
  const showDone = viewFilter === "all" || viewFilter === "done";

  function openEditDialog(kind, id, text) {
    setEditDialog({ open: true, kind, id, text: editableContent(text) });
  }

  function isLoading(key) {
    return activeActionKey === key;
  }

  function closeEditDialog() {
    setEditDialog({ open: false, kind: "note", id: null, text: "" });
  }

  async function submitEditDialog(event) {
    event.preventDefault();
    const nextText = String(editDialog.text || "").trim();
    if (!nextText || editDialog.id === null) {
      return;
    }
    if (editDialog.kind === "note") {
      await onEditNote(editDialog.id, nextText);
    } else {
      await onEditTodo(editDialog.id, nextText);
    }
    closeEditDialog();
  }

  return (
    <main className="workspace-view">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>{activeProject || "No project selected"}</h1>
          <p className="helper-text">Signed in as {session.email || "unknown"}</p>
        </div>
        <div className="header-actions">
          <select className="project-picker" value={activeProject || ""} onChange={(event) => onProjectChange(event.target.value)}>
            {projects.map((project) => (
              <option key={project.project} value={project.project}>
                {project.project} ({project.todo_count} todos)
              </option>
            ))}
          </select>
          <button className="btn" onClick={onRefresh}>
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
          {!isCreatingProject ? (
            <button className="btn btn-primary" onClick={onStartCreateProject}>
              New Project
            </button>
          ) : null}
          <button className="btn" onClick={onLogout}>
            Logout
          </button>
        </div>
      </header>

      {isCreatingProject ? (
        <section className="project-create-bar">
          <form
            className="project-create-form"
            onSubmit={(event) => {
              event.preventDefault();
              onCreateProject();
            }}
          >
            <label htmlFor="new-project-name">New project</label>
            <input
              id="new-project-name"
              value={newProjectName}
              onChange={(event) => onNewProjectNameChange(event.target.value)}
              placeholder="e.g. hiring-q3"
              maxLength={80}
              autoFocus
            />
            <button className="btn btn-primary" type="submit" disabled={isCreatingProjectSubmitting || !String(newProjectName || "").trim()}>
              {isCreatingProjectSubmitting ? "Creating..." : "Create"}
            </button>
            <button className="btn" type="button" onClick={onCancelCreateProject} disabled={isCreatingProjectSubmitting}>
              Cancel
            </button>
          </form>
        </section>
      ) : null}

      <section className="workspace-metrics">
        <Metric label="Notes" value={state.notes_count || 0} />
        <Metric label="Open Todos" value={state.todo_count || 0} />
        <Metric label="Pending Potentials" value={state.potential_pending_count || 0} />
        <Metric label="Last Update" value={state.updated_at || "-"} />
      </section>

      <section className="quick-toolbar">
        <div className="quick-actions">
          <button className="btn btn-primary" onClick={onQuickAddNote}>
            Focus Note Input (N)
          </button>
          <button className="btn btn-accent" onClick={onQuickAddTodo}>
            Focus Todo Input (T)
          </button>
          <button className="btn" onClick={onRefresh}>
            Refresh (R)
          </button>
        </div>
        <p className="keyboard-hint">Keyboard: N = note input, T = todo input, R = refresh</p>
      </section>

      <section className="filter-bar">
        <div className="filter-chip-group">
          {FILTERS.map((item) => (
            <FilterChip key={item.key} label={item.label} active={viewFilter === item.key} onClick={() => onViewFilterChange(item.key)} />
          ))}
        </div>
      </section>

      <section className="composer-grid">
        <form className="composer" onSubmit={onAddNote}>
          <label htmlFor="new-note">New note</label>
          <div>
            <input id="new-note" name="text" placeholder="Write a note update..." required />
            <button className="btn btn-primary" type="submit" disabled={isLoading("add-note")}>
              {isLoading("add-note") ? "Adding..." : "Add note"}
            </button>
          </div>
        </form>
        <form className="composer" onSubmit={onAddTodo}>
          <label htmlFor="new-todo">New todo</label>
          <div>
            <input id="new-todo" name="text" placeholder="Describe the next action..." required />
            <button className="btn btn-accent" type="submit" disabled={isLoading("add-todo")}>
              {isLoading("add-todo") ? "Adding..." : "Add todo"}
            </button>
          </div>
        </form>
      </section>

      <section className="workspace-grid">
        {showNotes ? (
          <SectionCard title="Notes" count={filteredNotes.length} className="notes-panel">
            <div className="section-tools">
              <input id="notes-filter" placeholder="Filter notes by text or section" value={noteQuery} onChange={(event) => onNoteQueryChange(event.target.value)} />
            </div>
            {filteredNotes.length ? (
              filteredNotes.map((note) => (
                <article className="item-row" key={`note-${note.id}`}>
                  <div>
                    <ItemMeta id={note.id} timestamp={extractInlineTimestamp(note.text)} />
                    <ItemText text={displayBody(note.text)} />
                  </div>
                  <RowActions>
                    <ActionButton onClick={() => openEditDialog("note", note.id, note.text)} disabled={isLoading(`edit-note-${note.id}`)}>
                      {isLoading(`edit-note-${note.id}`) ? "Saving..." : "Edit"}
                    </ActionButton>
                    <ActionButton onClick={() => onAiEdit("note", note.id)}>AI edit</ActionButton>
                    <ActionButton className="danger" onClick={() => onDismissNote(note.id)} disabled={isLoading(`dismiss-note-${note.id}`)}>
                      {isLoading(`dismiss-note-${note.id}`) ? "Dismissing..." : "Dismiss"}
                    </ActionButton>
                  </RowActions>
                </article>
              ))
            ) : (
              <EmptyState text="No matching notes." />
            )}
          </SectionCard>
        ) : null}

        {showTodos ? (
          <SectionCard title="Open Todos" count={filteredTodos.length} className="todos-panel">
            <div className="section-tools">
              <input id="todos-filter" placeholder="Filter todos" value={todoQuery} onChange={(event) => onTodoQueryChange(event.target.value)} />
            </div>

            {shortTermTodos.length ? <p className="section-divider">Short-term</p> : null}
            {shortTermTodos.map((todo) => (
              <article className="item-row" key={`todo-short-${todo.id}`}>
                <div>
                  <ItemMeta id={todo.id} timestamp={extractInlineTimestamp(todo.text)} />
                  <ItemText text={displayBody(todo.text)} />
                </div>
                <RowActions>
                  <ActionButton className="action-main" onClick={() => onCompleteTodo(todo.id)} disabled={isLoading(`complete-todo-${todo.id}`)}>
                    {isLoading(`complete-todo-${todo.id}`) ? "Completing..." : "Complete"}
                  </ActionButton>
                  <ActionButton onClick={() => onTodoLongTerm(todo.id)} disabled={isLoading(`mark-lt-${todo.id}`)}>
                    {isLoading(`mark-lt-${todo.id}`) ? "Marking..." : "Mark LT"}
                  </ActionButton>
                  <ActionButton onClick={() => openEditDialog("todo", todo.id, todo.text)} disabled={isLoading(`edit-todo-${todo.id}`)}>
                    {isLoading(`edit-todo-${todo.id}`) ? "Saving..." : "Edit"}
                  </ActionButton>
                  <ActionButton onClick={() => onAiEdit("todo", todo.id)}>AI edit</ActionButton>
                </RowActions>
              </article>
            ))}

            {longTermTodos.length ? <p className="section-divider">Long-term</p> : null}
            {longTermTodos.map((todo) => (
              <article className="item-row" key={`todo-long-${todo.id}`}>
                <div>
                  <ItemMeta
                    id={todo.id}
                    timestamp={extractInlineTimestamp(todo.text)}
                    extra={<span className="status status-promoted">Long-term</span>}
                  />
                  <ItemText text={displayBody(todo.text)} />
                </div>
                <RowActions>
                  <ActionButton className="action-main" onClick={() => onCompleteTodo(todo.id)} disabled={isLoading(`complete-todo-${todo.id}`)}>
                    {isLoading(`complete-todo-${todo.id}`) ? "Completing..." : "Complete"}
                  </ActionButton>
                  <ActionButton onClick={() => onTodoShortTerm(todo.id)} disabled={isLoading(`mark-st-${todo.id}`)}>
                    {isLoading(`mark-st-${todo.id}`) ? "Marking..." : "Mark ST"}
                  </ActionButton>
                  <ActionButton onClick={() => openEditDialog("todo", todo.id, todo.text)} disabled={isLoading(`edit-todo-${todo.id}`)}>
                    {isLoading(`edit-todo-${todo.id}`) ? "Saving..." : "Edit"}
                  </ActionButton>
                  <ActionButton onClick={() => onAiEdit("todo", todo.id)}>AI edit</ActionButton>
                </RowActions>
              </article>
            ))}

            {!filteredTodos.length ? <EmptyState text="No matching todos." /> : null}
          </SectionCard>
        ) : null}

        {showPotentials ? (
          <SectionCard title="Potential Actions" count={filteredPotentials.length}>
            <div className="section-tools section-tools-row">
              <input
                id="potentials-filter"
                placeholder="Filter potential actions"
                value={potentialQuery}
                onChange={(event) => onPotentialQueryChange(event.target.value)}
              />
              {reviewedPotentials.length ? (
                <button className="btn btn-ghost" onClick={() => setShowReviewedPotentials((prev) => !prev)} type="button">
                  {showReviewedPotentials ? "Hide reviewed" : `Show reviewed (${reviewedPotentials.length})`}
                </button>
              ) : null}
            </div>

            {pendingPotentials.length ? <p className="section-divider">Pending</p> : null}
            {pendingPotentials.map((potential) => (
              <article className="item-row" key={`potential-${potential.id}`}>
                <div>
                  <ItemMeta
                    id={potential.id}
                    timestamp={potential.timestamp}
                    extra={<span className={statusClass(potential.status)}>{potential.status}</span>}
                  />
                  <ItemText text={displayBody(potential.text)} />
                </div>
                <RowActions>
                  <ActionButton
                    className="positive action-main"
                    onClick={() => onApprovePotential(potential.id)}
                    disabled={potential.status !== "pending" || isLoading(`approve-potential-${potential.id}`)}
                  >
                    {isLoading(`approve-potential-${potential.id}`) ? "Approving..." : "Approve"}
                  </ActionButton>
                  <ActionButton
                    className="danger"
                    onClick={() => onRejectPotential(potential.id)}
                    disabled={potential.status !== "pending" || isLoading(`reject-potential-${potential.id}`)}
                  >
                    {isLoading(`reject-potential-${potential.id}`) ? "Rejecting..." : "Reject"}
                  </ActionButton>
                </RowActions>
              </article>
            ))}

            {showReviewedPotentials && reviewedPotentials.length ? <p className="section-divider">Reviewed</p> : null}
            {showReviewedPotentials
              ? reviewedPotentials.map((potential) => (
                  <article className="item-row" key={`potential-reviewed-${potential.id}`}>
                    <div>
                      <ItemMeta
                        id={potential.id}
                        timestamp={potential.timestamp}
                        extra={<span className={statusClass(potential.status)}>{potential.status}</span>}
                      />
                      <ItemText text={displayBody(potential.text)} />
                    </div>
                  </article>
                ))
              : null}

            {!filteredPotentials.length ? <EmptyState text="No matching potential actions." /> : null}
            {filteredPotentials.length && !hasVisiblePotentials ? <EmptyState text="Reviewed actions are hidden." /> : null}
          </SectionCard>
        ) : null}

        {showDone ? (
          <SectionCard title="Completed" count={state.done?.length || 0}>
            {state.done?.length ? (
              <div className="section-tools section-tools-row">
                <div />
                <button className="btn btn-ghost" onClick={() => setShowCompletedItems((prev) => !prev)} type="button">
                  {showCompletedItems ? "Hide completed" : `Show completed (${state.done.length})`}
                </button>
              </div>
            ) : null}
            {showCompletedItems ? (
              state.done?.length ? (
                state.done.map((item, index) => (
                  <article className="item-row" key={`done-${index}`}>
                    <div>
                      <ItemMeta id={index + 1} timestamp={item.timestamp} />
                      <ItemText text={displayBody(item.text)} />
                    </div>
                  </article>
                ))
              ) : (
                <EmptyState text="No completed todos archived yet." />
              )
            ) : (
              <EmptyState text="Completed items are hidden." />
            )}
          </SectionCard>
        ) : null}
      </section>

      <footer className="workspace-footer">
        <p>Updated at: {state.updated_at || "-"}</p>
        <p>
          {state.notes_count || 0} notes, {state.todo_count || 0} todos, {state.potential_pending_count || 0} pending
          potentials
        </p>
      </footer>

      <DialogModal
        open={editDialog.open}
        title={editDialog.kind === "note" ? "Edit note" : "Edit todo"}
        actions={
          <>
            <button className="btn" type="button" onClick={closeEditDialog}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              type="submit"
              form="edit-item-form"
              disabled={!String(editDialog.text || "").trim() || (editDialog.kind === "note" ? isLoading(`edit-note-${editDialog.id}`) : isLoading(`edit-todo-${editDialog.id}`))}
            >
              {editDialog.kind === "note"
                ? (isLoading(`edit-note-${editDialog.id}`) ? "Saving..." : "Save")
                : (isLoading(`edit-todo-${editDialog.id}`) ? "Saving..." : "Save")}
            </button>
          </>
        }
      >
        <form id="edit-item-form" className="dialog-form" onSubmit={submitEditDialog}>
          <label htmlFor="edit-item-text">Content</label>
          <textarea
            id="edit-item-text"
            value={editDialog.text}
            onChange={(event) => setEditDialog((prev) => ({ ...prev, text: event.target.value }))}
            rows={5}
            autoFocus
          />
        </form>
      </DialogModal>
    </main>
  );
}

export function mapAiEditAction(kind) {
  return kind === "note" ? ACTION_TYPES.AI_SUGGEST_EDIT_NOTE : ACTION_TYPES.AI_SUGGEST_EDIT_TODO;
}

export function mapEditAction(kind) {
  return kind === "note" ? ACTION_TYPES.EDIT_NOTE : ACTION_TYPES.EDIT_TODO;
}
