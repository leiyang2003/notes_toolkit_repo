export default function ToastStack({ toasts, onDismiss }) {
  return (
    <aside className="toast-stack" aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <section key={toast.id} className={`toast toast-${toast.kind || "info"}`}>
          <div>
            <p className="toast-title">{toast.title}</p>
            <p className="toast-message">{toast.message}</p>
          </div>
          <button className="toast-close" onClick={() => onDismiss(toast.id)} aria-label="Dismiss">
            x
          </button>
        </section>
      ))}
    </aside>
  );
}
