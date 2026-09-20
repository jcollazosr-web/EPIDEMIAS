// bold-webhook — Recibe notificaciones de pago de Bold (checkout.bold.co)
// y activa el plan PRO automáticamente para el usuario cuyo correo
// coincida con el correo del pagador (payer_email).
//
// Seguridad: verifica la firma HMAC-SHA256 enviada por Bold en el
// header 'x-bold-signature' antes de procesar nada — sin esto,
// cualquiera podría enviar una solicitud falsa y activar PRO gratis.
//
// Variables de entorno requeridas (configurar como "secrets" de esta
// función en Supabase, NUNCA en el código):
//   BOLD_WEBHOOK_SECRET   -> llave secreta del botón de pagos de Bold
//   SUPABASE_URL          -> se inyecta automáticamente
//   SUPABASE_SERVICE_ROLE_KEY -> se inyecta automáticamente

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const BOLD_WEBHOOK_SECRET = Deno.env.get("BOLD_WEBHOOK_SECRET") || "";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

async function verificarFirma(cuerpoCrudo: string, firmaRecibida: string): Promise<boolean> {
  if (!BOLD_WEBHOOK_SECRET) return false; // nunca procesar sin llave configurada

  const cuerpoBase64 = btoa(cuerpoCrudo);
  const encoder = new TextEncoder();
  const claveCripto = await crypto.subtle.importKey(
    "raw",
    encoder.encode(BOLD_WEBHOOK_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const firmaBuffer = await crypto.subtle.sign("HMAC", claveCripto, encoder.encode(cuerpoBase64));
  const firmaHex = Array.from(new Uint8Array(firmaBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  // Comparación en tiempo constante (evita timing attacks)
  if (firmaHex.length !== firmaRecibida.length) return false;
  let diferencia = 0;
  for (let i = 0; i < firmaHex.length; i++) {
    diferencia |= firmaHex.charCodeAt(i) ^ firmaRecibida.charCodeAt(i);
  }
  return diferencia === 0;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const cuerpoCrudo = await req.text();
  const firmaRecibida = req.headers.get("x-bold-signature") || "";

  const firmaValida = await verificarFirma(cuerpoCrudo, firmaRecibida);
  if (!firmaValida) {
    return new Response(JSON.stringify({ error: "Firma inválida" }), { status: 400 });
  }

  let evento: any;
  try {
    evento = JSON.parse(cuerpoCrudo);
  } catch {
    return new Response(JSON.stringify({ error: "JSON inválido" }), { status: 400 });
  }

  const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);

  // Solo actuamos sobre ventas aprobadas
  if (evento.type !== "SALE_APPROVED") {
    return new Response(JSON.stringify({ mensaje: "Evento ignorado (no es SALE_APPROVED)" }), { status: 200 });
  }

  const datos = evento.data || {};
  const paymentId: string = datos.payment_id || evento.subject || crypto.randomUUID();
  const payerEmail: string | undefined = datos.payer_email;
  const monto: number | undefined = datos.amount?.total;

  // Idempotencia: si ya procesamos este payment_id, no lo repetimos.
  const { data: yaExiste } = await supabase
    .from("pagos_bold_procesados")
    .select("payment_id")
    .eq("payment_id", paymentId)
    .maybeSingle();

  if (yaExiste) {
    return new Response(JSON.stringify({ mensaje: "Pago ya procesado anteriormente" }), { status: 200 });
  }

  if (!payerEmail) {
    await supabase.from("pagos_bold_procesados").insert({
      payment_id: paymentId, payer_email: null, monto, estado: "sin_match",
      detalle: "La notificación no incluyó correo del pagador",
    });
    return new Response(JSON.stringify({ mensaje: "Sin correo del pagador, registrado para revisión manual" }), { status: 200 });
  }

  // Buscar el usuario por correo (insensible a mayúsculas)
  const { data: usuarios, error: errorBusqueda } = await supabase.auth.admin.listUsers();
  const usuarioEncontrado = usuarios?.users?.find(
    (u: any) => u.email?.toLowerCase() === payerEmail.toLowerCase(),
  );

  if (errorBusqueda || !usuarioEncontrado) {
    await supabase.from("pagos_bold_procesados").insert({
      payment_id: paymentId, payer_email: payerEmail, monto, estado: "sin_match",
      detalle: "No se encontró ningún usuario de EpiScan con ese correo",
    });
    return new Response(JSON.stringify({ mensaje: "Correo sin coincidencia, registrado para revisión manual" }), { status: 200 });
  }

  // Activar plan PRO
  const { error: errorUpdate } = await supabase
    .from("perfiles")
    .update({ plan: "pro", plan_actualizado_en: new Date().toISOString() })
    .eq("usuario_id", usuarioEncontrado.id);

  await supabase.from("pagos_bold_procesados").insert({
    payment_id: paymentId, payer_email: payerEmail, usuario_id: usuarioEncontrado.id, monto,
    estado: errorUpdate ? "error" : "activado",
    detalle: errorUpdate ? String(errorUpdate.message) : "Plan PRO activado automáticamente",
  });

  return new Response(JSON.stringify({ mensaje: errorUpdate ? "Error al activar el plan" : "Plan PRO activado" }), {
    status: 200,
  });
});
