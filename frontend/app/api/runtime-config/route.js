export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json({
    backendBaseUrl: String(process.env.BACKEND_BASE_URL || "").trim(),
  });
}
