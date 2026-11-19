import { createClient } from "npm:@supabase/supabase-js@2.57.0";

const projectUrl = Deno.env.get("SUPABASE_URL") ?? "";
const secretKey = (() => {
  try {
    const keys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}");
    if (typeof keys.default === "string" && keys.default) return keys.default;
  } catch { /* fallback to legacy server-side key */ }
  return Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
})();
const admin = createClient(projectUrl, secretKey, {
  auth: { autoRefreshToken: false, persistSession: false },
});

const safeOrigin = (origin: string) =>
  origin === "https://nayibi21.github.io" ||
  /^http:\/\/(?:localhost|127\.0\.0\.1)(?::\d{2,5})?$/.test(origin) ||
  /^http:\/(?:\/10\.|\/192\.168\.|\/172\.(?:1[6-9]|2\d|3[01])\.)(?:\d{1,3}\.){2}\d{1,3}(?::\d{2,5})?$/.test(origin);
const headersFor = (origin: string) => ({
  "Access-Control-Allow-Origin": safeOrigin(origin) ? origin : "https://nayibi21.github.io",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Vary": "Origin",
  "Content-Type": "application/json; charset=utf-8",
});
const respond = (origin: string, status: number, body: Record<string, unknown>) =>
  new Response(JSON.stringify(body), { status, headers: headersFor(origin) });

Deno.serve(async (req: Request) => {
  const origin = req.headers.get("origin") ?? "";
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: headersFor(origin) });
  if (req.method !== "POST") return respond(origin, 405, { error: "Método no permitido." });
  if (origin && !safeOrigin(origin)) return respond(origin, 403, { error: "Origen no autorizado." });
  try {
    const raw = await req.text();
    if (raw.length > 2048) return respond(origin, 413, { error: "Solicitud demasiado grande." });
    const body = JSON.parse(raw);
    const usuario = typeof body?.usuario === "string" ? body.usuario.trim().toLowerCase() : "";
    const contrasena = typeof body?.contrasena === "string" ? body.contrasena : "";
    if (!/^[a-z0-9][a-z0-9._-]{2,31}$/.test(usuario)) {
      return respond(origin, 400, { error: "Usuario: 3 a 32 letras minúsculas, números, punto, guion o guion bajo." });
    }
    if (contrasena.length < 8 || contrasena.length > 72) {
      return respond(origin, 400, { error: "Contraseña: entre 8 y 72 caracteres." });
    }
    if (!projectUrl || !secretKey) return respond(origin, 503, { error: "El servicio de registro no está configurado." });

    // Solo guardamos el hash del origen de red, nunca la IP ni la contraseña.
    const ip = req.headers.get("x-real-ip") ||
      req.headers.get("cf-connecting-ip") ||
      req.headers.get("x-forwarded-for")?.split(",").at(-1)?.trim() || "sin-ip";
    const bytes = new TextEncoder().encode(ip + "|" + secretKey);
    const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
      .map(n => n.toString(16).padStart(2, "0")).join("");
    const rate = await admin.rpc("mini_consumir_cupo_registro", { p_clave: hash });
    if (rate.error) return respond(origin, 503, { error: "No se pudo validar el registro. Inténtalo de nuevo." });
    if (!rate.data) return respond(origin, 429, { error: "Se alcanzó el límite temporal de registros desde esta red. Intenta más tarde." });

    // Dirección técnica reservada: no es un correo real, jamás se envían correos a ella.
    const email = usuario + "@members.mini-yolotzin.example.com";
    const result = await admin.auth.admin.createUser({
      email, password: contrasena, email_confirm: true,
      user_metadata: { username: usuario },
    });
    if (result.error) {
      const duplicate = result.error.status === 422 ||
        /already registered|already exists|unique/i.test(result.error.message || "");
      return respond(origin, duplicate ? 409 : 400, {
        error: duplicate ? "Ese usuario ya existe. Elige otro o inicia sesión." : "No fue posible registrar ese usuario. Intenta con otro nombre.",
      });
    }
    return respond(origin, 201, { ok: true, usuario });
  } catch {
    return respond(origin, 400, { error: "No se pudo procesar el registro." });
  }
});
