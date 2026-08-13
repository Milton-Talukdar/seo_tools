/**
 * Shared Supabase REST helper for Cloudflare Pages Functions.
 * Files prefixed with '_' are not treated as routes by Pages Functions.
 */

export function sbHeaders(env) {
  return {
    apikey: env.SUPABASE_ANON_KEY,
    Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`,
    Accept: "application/json",
  };
}

export async function sbFetch(env, path) {
  const url = `${env.SUPABASE_URL}/rest/v1${path}`;
  const res = await fetch(url, { headers: sbHeaders(env) });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Supabase ${res.status}: ${text}`);
  }
  return res.json();
}

export function jsonError(message, status = 500) {
  return Response.json({ error: message }, { status, headers: { "Content-Type": "application/json" } });
}
