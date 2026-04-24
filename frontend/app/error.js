"use client";

export default function Error({ error, reset }) {
  return (
    <main className="error-screen">
      <div className="error-card">
        <p className="eyebrow">Unexpected Error</p>
        <h1>The workspace crashed.</h1>
        <p>{error?.message || "An unknown UI error happened."}</p>
        <button className="btn btn-primary" onClick={() => reset()}>
          Retry
        </button>
      </div>
    </main>
  );
}
