import { useState } from "react";
import { ACTION_TYPES } from "../lib/api-client";

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

function editableContent(text) {
  let raw = String(text || "").trim();
  const timestampPrefix = /^\s*\[\d{4}-\d{2}-\d{2}[^\]]*\]\s*/;
  const longTermPrefix = /^\s*\[LT\]\s*/i;

  // Strip system-managed metadata prefixes until content starts.
  while (true) {
    const next = raw.replace(longTermPrefix, "").replace(timestampPrefix, "").trim();
    if (next === raw) {
      break;
    }
    raw = next;
  }
  return raw;
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
}) {
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

  return (
    <main className="workspace-view">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>{activeProject || "No project selected"}</h1>
          <p className="helper-text">Signed in as {session.email || "unknown"}</p>
        </div>
        <div className="header-actions">
          <select
            className="project-picker"
            value={activeProject || ""}
            onChange={(event) => onProjectChange(event.target.value)}
          >
            {projects.map((project) => (
              <option key={project.project} value={project.project}>
                {project.project} ({project.todo_count} todos)
              </option>
            ))}
          </select>
          <button className="btn" onClick={onRefresh}>
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
          <button className="btn" onClick={onLogout}>
            Logout
          </button>
        </div>
      </header>

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
            <FilterChip
              key={item.key}
              label={item.label}
              active={viewFilter === item.key}
              onClick={() => onViewFilterChange(item.key)}
            />
          ))}
        </div>
      </section>

      <section className="composer-grid">
        <form className="composer" onSubmit={onAddNote}>
          <label htmlFor="new-note">New note</label>
          <div>
            <input id="new-note" name="text" placeholder="Write a note update..." required />
            <button className="btn btn-primary" type="submit">
              Add note
            </button>
          </div>
        </form>
        <form className="composer" onSubmit={onAddTodo}>
          <label htmlFor="new-todo">New todo</label>
          <div>
            <input id="new-todo" name="text" placeholder="Describe the next action..." required />
            <button className="btn btn-accent" type="submit">
              Add todo
            </button>
          </div>
        </form>
      </section>

      <section className="workspace-grid">
        {showNotes ? (
          <SectionCard title="Notes" count={filteredNotes.length} className="notes-panel">
            <div className="section-tools">
              <input
                id="notes-filter"
                placeholder="Filter notes by text or section"
                value={noteQuery}
                onChange={(event) => onNoteQueryChange(event.target.value)}
              />
            </div>
            {filteredNotes.length ? (
              filteredNotes.map((note) => (
                <article className="item-row" key={`note-${note.id}`}>
                  <div>
                    <p className="item-meta">
                      <span className="id-chip">#{note.id}</span> {note.section || "General"}
                    </p>
                    <ItemText text={note.text} />
                  </div>
                  <RowActions>
                    <ActionButton
                      onClick={() => {
                        const nextText = window.prompt("Edit note text", editableContent(note.text));
                        if (nextText && nextText.trim()) {
                          onEditNote(note.id, nextText.trim());
                        }
                      }}
                    >
                      Edit
                    </ActionButton>
                    <ActionButton onClick={() => onAiEdit("note", note.id)}>AI edit</ActionButton>
                    <ActionButton className="danger" onClick={() => onDismissNote(note.id)}>
                      Dismiss
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
              <input
                id="todos-filter"
                placeholder="Filter todos"
                value={todoQuery}
                onChange={(event) => onTodoQueryChange(event.target.value)}
              />
            </div>

            {shortTermTodos.length ? <p className="section-divider">Short-term</p> : null}
            {shortTermTodos.map((todo) => (
              <article className="item-row" key={`todo-short-${todo.id}`}>
                <div>
                  <p className="item-meta">
                    <span className="id-chip">#{todo.id}</span>
                  </p>
                  <ItemText text={todo.text} />
                </div>
                <RowActions>
                  <ActionButton className="action-main" onClick={() => onCompleteTodo(todo.id)}>
                    Complete
                  </ActionButton>
                  <ActionButton onClick={() => onTodoLongTerm(todo.id)}>Mark LT</ActionButton>
                  <ActionButton
                    onClick={() => {
                      const nextText = window.prompt("Edit todo text", editableContent(todo.text));
                      if (nextText && nextText.trim()) {
                        onEditTodo(todo.id, nextText.trim());
                      }
                    }}
                  >
                    Edit
                  </ActionButton>
                  <ActionButton onClick={() => onAiEdit("todo", todo.id)}>AI edit</ActionButton>
                </RowActions>
              </article>
            ))}

            {longTermTodos.length ? <p className="section-divider">Long-term</p> : null}
            {longTermTodos.map((todo) => (
              <article className="item-row" key={`todo-long-${todo.id}`}>
                <div>
                  <p className="item-meta">
                    <span className="id-chip">#{todo.id}</span>
                    <span className="status status-promoted">Long-term</span>
                  </p>
                  <ItemText text={todo.text} />
                </div>
                <RowActions>
                  <ActionButton className="action-main" onClick={() => onCompleteTodo(todo.id)}>
                    Complete
                  </ActionButton>
                  <ActionButton onClick={() => onTodoShortTerm(todo.id)}>Mark ST</ActionButton>
                  <ActionButton
                    onClick={() => {
                      const nextText = window.prompt("Edit todo text", editableContent(todo.text));
                      if (nextText && nextText.trim()) {
                        onEditTodo(todo.id, nextText.trim());
                      }
                    }}
                  >
                    Edit
                  </ActionButton>
                  <ActionButton onClick={() => onAiEdit("todo", todo.id)}>AI edit</ActionButton>
                </RowActions>
              </article>
            ))}

            {!filteredTodos.length ? (
              <EmptyState text="No matching todos." />
            ) : null}
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
                <button
                  className="btn btn-ghost"
                  onClick={() => setShowReviewedPotentials((prev) => !prev)}
                  type="button"
                >
                  {showReviewedPotentials ? "Hide reviewed" : `Show reviewed (${reviewedPotentials.length})`}
                </button>
              ) : null}
            </div>

            {pendingPotentials.length ? <p className="section-divider">Pending</p> : null}
            {pendingPotentials.map((potential) => (
              <article className="item-row" key={`potential-${potential.id}`}>
                <div>
                  <p className="item-meta">
                    <span className="id-chip">#{potential.id}</span>{" "}
                    <span className={statusClass(potential.status)}>{potential.status}</span>
                  </p>
                  <ItemText text={potential.text} />
                </div>
                <RowActions>
                  <ActionButton
                    className="positive action-main"
                    onClick={() => onApprovePotential(potential.id)}
                    disabled={potential.status !== "pending"}
                  >
                    Approve
                  </ActionButton>
                  <ActionButton
                    className="danger"
                    onClick={() => onRejectPotential(potential.id)}
                    disabled={potential.status !== "pending"}
                  >
                    Reject
                  </ActionButton>
                </RowActions>
              </article>
            ))}

            {showReviewedPotentials && reviewedPotentials.length ? <p className="section-divider">Reviewed</p> : null}
            {showReviewedPotentials
              ? reviewedPotentials.map((potential) => (
                  <article className="item-row" key={`potential-reviewed-${potential.id}`}>
                    <div>
                      <p className="item-meta">
                        <span className="id-chip">#{potential.id}</span>{" "}
                        <span className={statusClass(potential.status)}>{potential.status}</span>
                      </p>
                      <ItemText text={potential.text} />
                    </div>
                  </article>
                ))
              : null}

            {!filteredPotentials.length ? <EmptyState text="No matching potential actions." /> : null}
            {filteredPotentials.length && !hasVisiblePotentials ? (
              <EmptyState text="Reviewed actions are hidden." />
            ) : null}
          </SectionCard>
        ) : null}

        {showDone ? (
          <SectionCard title="Completed" count={state.done?.length || 0}>
            {state.done?.length ? (
              <div className="section-tools section-tools-row">
                <div />
                <button
                  className="btn btn-ghost"
                  onClick={() => setShowCompletedItems((prev) => !prev)}
                  type="button"
                >
                  {showCompletedItems ? "Hide completed" : `Show completed (${state.done.length})`}
                </button>
              </div>
            ) : null}
            {showCompletedItems ? (
              state.done?.length ? (
                state.done.map((item, index) => (
                  <article className="item-row" key={`done-${index}`}>
                    <div>
                      <p className="item-meta">{item.timestamp}</p>
                      <ItemText text={item.text} />
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
    </main>
  );
}

export function mapAiEditAction(kind) {
  return kind === "note" ? ACTION_TYPES.AI_SUGGEST_EDIT_NOTE : ACTION_TYPES.AI_SUGGEST_EDIT_TODO;
}

export function mapEditAction(kind) {
  return kind === "note" ? ACTION_TYPES.EDIT_NOTE : ACTION_TYPES.EDIT_TODO;
}
