// sso-hce -- Ingreso único desde la Historia Clínica Electrónica (HCE).
//
// La HCE abre EpiScan con ?sso=<pase>. EpiScan le envía el pase a esta función, que:
//   1. verifica la firma HMAC-SHA256 con el secreto compartido (tabla privada sso_secreto, sin políticas RLS: solo
//      la lee la service_role; o la variable SSO_HCE_SECRET),
//   2. revisa que no esté vencido y que no se haya usado antes (tabla sso_nonces),
//   3. crea la cuenta de EpiScan si el correo aún no existe (confirmada),
//   4. genera un enlace mágico y devuelve SOLO su token_hash; EpiScan lo canjea con verify_otp para abrir la
//      sesión del usuario (con RLS normal). La service_role key nunca sale del servidor de Supabase.
//
// Con accion:"crear" solo crea la cuenta (sin sesión): la HCE lo usa al registrar un usuario o su correo.
// Pase: base64url(JSON {email, nombre, exp, nonce, iss:"hce", accion?}) + "." + hex(HMAC-SHA256(parte1, secreto)).
// Desplegar con verify_jwt = false: la autenticidad la da la firma del pase.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const enc = new TextEncoder();
let SECRETO = Deno.env.get("SSO_HCE_SECRET") || "";

function respuesta(cuerpo: unknown, status = 200) {
  return new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } });
}

function base64urlATexto(s: string): string {
  let b = s.replace(/-/g, "+").replace(/_/g, "/");
  while (b.length % 4) b += "=";
  return new TextDecoder().decode(Uint8Array.from(atob(b), (c) => c.charCodeAt(0)));
}

async function hmacHex(mensaje: string): Promise<string> {
  const clave = await crypto.subtle.importKey("raw", enc.encode(SECRETO), { name: "HMAC", hash: "SHA-256" }, false,
    ["sign"]);
  const firma = new Uint8Array(await crypto.subtle.sign("HMAC", clave, enc.encode(mensaje)));
  return Array.from(firma).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function igualesSeguro(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return respuesta({ error: "Método no permitido" }, 405);
  const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, { auth: { persistSession: false } });
  if (SECRETO.length < 32) {
    const { data } = await supabase.from("sso_secreto").select("valor").eq("clave", "hce").maybeSingle();
    SECRETO = data?.valor || "";
  }
  if (SECRETO.length < 32) return respuesta({ error: "El ingreso único no está configurado." }, 503);

  let token = "";
  try {
    token = String((await req.json()).token || "");
  } catch {
    return respuesta({ error: "Solicitud inválida." }, 400);
  }
  const [parte, firma] = token.split(".");
  if (!parte || !firma || !igualesSeguro(await hmacHex(parte), firma.toLowerCase())) {
    return respuesta({ error: "Pase de ingreso inválido." }, 401);
  }

  let datos: { email?: string; nombre?: string; exp?: number; nonce?: string; iss?: string; accion?: string };
  try {
    datos = JSON.parse(base64urlATexto(parte));
  } catch {
    return respuesta({ error: "Pase de ingreso inválido." }, 401);
  }
  const email = String(datos.email || "").trim().toLowerCase();
  if (datos.iss !== "hce" || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || !datos.nonce) {
    return respuesta({ error: "Pase de ingreso inválido." }, 401);
  }
  if (!datos.exp || datos.exp * 1000 < Date.now()) return respuesta({ error: "El pase de ingreso venció." }, 401);

  // Un solo uso por pase
  const { error: errorNonce } = await supabase.from("sso_nonces").insert({ nonce: String(datos.nonce).slice(0, 80) });
  if (errorNonce) return respuesta({ error: "Este pase de ingreso ya se usó." }, 401);
  await supabase.from("sso_nonces").delete().lt("usado_en", new Date(Date.now() - 2 * 86400000).toISOString());

  // Crear la cuenta si no existe (ya confirmada: la persona viene autenticada por la HCE)
  const { error: errorCrear } = await supabase.auth.admin.createUser({
    email, email_confirm: true, user_metadata: { nombre: datos.nombre || "", origen: "hce" },
  });
  if (errorCrear && !/already|registered|exists/i.test(errorCrear.message)) {
    return respuesta({ error: "No se pudo preparar la cuenta de EpiScan." }, 500);
  }
  // Solo crear la cuenta (la HCE la crea al registrar el usuario o su correo), sin abrir sesión
  if (datos.accion === "crear") return respuesta({ creada: !errorCrear, email });

  const { data, error } = await supabase.auth.admin.generateLink({ type: "magiclink", email });
  if (error || !data?.properties?.hashed_token) {
    return respuesta({ error: "No se pudo iniciar la sesión." }, 500);
  }
  return respuesta({ token_hash: data.properties.hashed_token, email });
});
