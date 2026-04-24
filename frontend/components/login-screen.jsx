export default function LoginScreen({ onLogin, backendBaseUrl }) {
  return (
    <main className="login-view">
      <section className="login-hero">
        <p className="eyebrow">Notes Toolkit</p>
        <h1>Capture signal. Ship faster.</h1>
        <p>
          One workspace for notes, todos, potential actions, and AI-assisted edits. Sign in with Google to load your
          private vault.
        </p>
        <button className="btn btn-primary" onClick={onLogin}>
          Continue with Google
        </button>
        <p className="helper-text">Backend: {backendBaseUrl || "same origin"}</p>
      </section>
      <section className="login-panel">
        <h2>What you can do</h2>
        <ul>
          <li>Track notes and todos in one timeline.</li>
          <li>Approve or reject potential actions quickly.</li>
          <li>Use AI edit suggestions before committing changes.</li>
          <li>Stay synced across desktop and mobile.</li>
        </ul>
      </section>
    </main>
  );
}
