// Proxy same-origin ke API Gateway (dipakai di preview lokal; di Amplify
// browser memanggil API GW langsung sehingga route ini tidak terpakai).
export const dynamic = "force-dynamic";

const UPSTREAM = process.env.API_UPSTREAM || "";

async function forward(req: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  if (!UPSTREAM) {
    return Response.json({ error: "API_UPSTREAM not configured" }, { status: 500 });
  }
  const { path } = await ctx.params;
  const qs = new URL(req.url).search;
  const url = `${UPSTREAM}/${(path || []).join("/")}${qs}`;
  const headers = new Headers();
  for (const k of ["authorization", "content-type"]) {
    const v = req.headers.get(k);
    if (v) headers.set(k, v);
  }
  try {
    const res = await fetch(url, {
      method: req.method,
      headers,
      body: req.method !== "GET" && req.method !== "HEAD" ? await req.text() : undefined,
    });
    const text = await res.text();
    return new Response(text, {
      status: res.status,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch (e) {
    return Response.json({ error: `proxy: ${(e as Error).message}` }, { status: 502 });
  }
}

export {
  forward as GET,
  forward as POST,
  forward as DELETE,
  forward as PUT,
  forward as OPTIONS,
};
