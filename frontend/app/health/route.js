export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json({
    ok: true,
    service: "notes-toolkit-frontend",
    framework: "nextjs",
  });
}
