export async function loadRuntimeConfig() {
  const response = await fetch("/api/runtime-config", {
    method: "GET",
    cache: "no-store",
  });
  if (!response.ok) {
    return { backendBaseUrl: "" };
  }

  const payload = await response.json();
  return {
    backendBaseUrl: String(payload.backendBaseUrl || "").trim(),
  };
}
