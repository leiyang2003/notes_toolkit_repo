export function DialogModal({ open, title, children, actions }) {
  if (!open) {
    return null;
  }

  return (
    <div className="dialog-overlay" role="presentation">
      <section className="dialog-modal" role="dialog" aria-modal="true" aria-label={title}>
        <header className="dialog-header">
          <h3>{title}</h3>
        </header>
        <div className="dialog-body">{children}</div>
        <footer className="dialog-actions">{actions}</footer>
      </section>
    </div>
  );
}
