// whatsapp-webhook -- Recibe mensajes de WhatsApp (vía Twilio) y
// registra casos nuevos directamente, sin que el usuario tenga que
// abrir EpiScan. Formato del mensaje: solo un número de casos nuevos,
// opcionalmente seguido de texto libre (que por ahora se ignora, para
// mantener el formato v1 simple): ej. "5" o "5 Barrio San José".
//
// Seguridad: verifica la firma de Twilio (X-Twilio-Signature) antes de
// procesar nada.
//
// Variables de entorno requeridas (Secrets de esta función):
//   TWILIO_AUTH_TOKEN     -> token de autenticación de tu cuenta Twilio
//   SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY -> inyectadas automáticamente

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const TWILIO_AUTH_TOKEN = Deno.env.get("TWILIO_AUTH_TOKEN") || "";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

async function verificarFirmaTwilio(url: string, params: Record<string, string>, firmaRecibida: string): Promise<boolean> {
  if (!TWILIO_AUTH_TOKEN) return false;
  const claves = Object.keys(params).sort();
  let datos = url;
  for (const k of claves) datos += k + params[k];

  const encoder = new TextEncoder();
  const claveCripto = await crypto.subtle.importKey("raw", encoder.encode(TWILIO_AUTH_TOKEN), { name: "HMAC", hash: "SHA-1" }, false, ["sign"]);
  const firmaBuffer = await crypto.subtle.sign("HMAC", claveCripto, encoder.encode(datos));
  const firmaBase64 = btoa(String.fromCharCode(...new Uint8Array(firmaBuffer)));
  return firmaBase64 === firmaRecibida;
}

function respuestaTwiml(texto: string): Response {
  const escapado = texto.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const xml = `<?xml version="1.0" encoding="UTF-8"?><Response><Message>${escapado}</Message></Response>`;
  return new Response(xml, { headers: { "Content-Type": "text/xml" } });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });

  const formData = await req.formData();
  const params: Record<string, string> = {};
  for (const [k, v] of formData.entries()) params[k] = String(v);

  const firmaRecibida = req.headers.get("X-Twilio-Signature") || "";
  const firmaValida = await verificarFirmaTwilio(req.url, params, firmaRecibida);
  if (!firmaValida) {
    return new Response("Firma inválida", { status: 403 });
  }

  const numeroDesde = (params["From"] || "").replace("whatsapp:", "").trim();
  const cuerpoMensaje = (params["Body"] || "").trim();

  const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);

  const registrarLog = async (usuario_id: string | null, resultado: string, detalle: string) => {
    await supabase.from("reportes_whatsapp_log").insert({
      telefono: numeroDesde, usuario_id, mensaje_recibido: cuerpoMensaje, resultado, detalle,
    });
  };

  // --- Comandos de administrador: "PRO correo@x.com" / "GRATIS correo@x.com" ---
  // Solo funcionan si el mensaje viene del número configurado como
  // ADMIN_WHATSAPP_NOTIFICACIONES en configuracion_global.
  const comandoAdmin = cuerpoMensaje.match(/^(PRO|GRATIS|FREE)\s+(\S+@\S+)$/i);
  if (comandoAdmin) {
    const { data: numeroAdminConfig } = await supabase
      .from("configuracion_global").select("valor").eq("clave", "ADMIN_WHATSAPP_NOTIFICACIONES").maybeSingle();

    if (numeroAdminConfig?.valor && numeroAdminConfig.valor.replace(/\s/g, "") === numeroDesde.replace(/\s/g, "")) {
      const nuevoPlan = comandoAdmin[1].toUpperCase() === "PRO" ? "pro" : "gratis";
      const correoObjetivo = comandoAdmin[2];

      const { data: usuarios } = await supabase.auth.admin.listUsers();
      const usuarioObjetivo = usuarios?.users?.find((u: any) => u.email?.toLowerCase() === correoObjetivo.toLowerCase());

      if (!usuarioObjetivo) {
        await registrarLog(null, "error", `Comando admin: correo no encontrado (${correoObjetivo})`);
        return respuestaTwiml(`No encontré ningún usuario de EpiScan con el correo ${correoObjetivo}.`);
      }

      const { error: errorPlan } = await supabase.from("perfiles")
        .update({ plan: nuevoPlan, plan_actualizado_en: new Date().toISOString() })
        .eq("usuario_id", usuarioObjetivo.id);

      if (errorPlan) {
        await registrarLog(usuarioObjetivo.id, "error", String(errorPlan.message));
        return respuestaTwiml(`❌ No se pudo actualizar el plan de ${correoObjetivo}.`);
      }

      await registrarLog(usuarioObjetivo.id, "registrado", `Plan actualizado a ${nuevoPlan} vía comando admin`);
      return respuestaTwiml(`✅ ${correoObjetivo} ahora tiene el plan ${nuevoPlan.toUpperCase()}.`);
    }
    // Si el número no coincide con el admin configurado, el mensaje
    // sigue de largo y se procesa como un reporte de casos normal
    // (por si un usuario normal reporta un texto que casualmente
    // empieza así).
  }

  const { data: perfil } = await supabase
    .from("perfiles")
    .select("usuario_id, brote_whatsapp_defecto, via_whatsapp_defecto")
    .eq("telefono_whatsapp", numeroDesde)
    .maybeSingle();

  if (!perfil) {
    await registrarLog(null, "sin_reconocer", "Número no configurado en ningún perfil");
    return respuestaTwiml("No reconocemos este número. Configura tu WhatsApp en EpiScan (menú lateral) primero.");
  }

  if (!perfil.brote_whatsapp_defecto) {
    await registrarLog(perfil.usuario_id, "sin_reconocer", "Sin brote configurado para WhatsApp");
    return respuestaTwiml("No tienes un brote configurado para reportes por WhatsApp. Configúralo en EpiScan.");
  }

  const coincidencia = cuerpoMensaje.match(/^(\d+)/);
  if (!coincidencia) {
    await registrarLog(perfil.usuario_id, "error_formato", "Mensaje no empieza con un número");
    return respuestaTwiml("No entendí el mensaje. Envía solo el número de casos nuevos de hoy, ej: '5'.");
  }

  const casosNuevos = parseInt(coincidencia[1], 10);
  const hoy = new Date().toISOString().split("T")[0];

  // Busca si ya hay un reporte hoy para sumar (varios mensajes en el
  // mismo día se ACUMULAN, no se sobrescriben -- tiene más sentido
  // para reportes rápidos de campo a lo largo del día).
  const { data: existente } = await supabase
    .from("registros_diarios")
    .select("id, casos_nuevos")
    .eq("usuario_id", perfil.usuario_id)
    .eq("brote_id", perfil.brote_whatsapp_defecto)
    .eq("fecha", hoy)
    .eq("via_contagio_id", perfil.via_whatsapp_defecto)
    .is("ubicacion_id", null)
    .maybeSingle();

  let error;
  let totalDia = casosNuevos;
  if (existente) {
    totalDia = existente.casos_nuevos + casosNuevos;
    ({ error } = await supabase.from("registros_diarios").update({ casos_nuevos: totalDia }).eq("id", existente.id));
  } else {
    ({ error } = await supabase.from("registros_diarios").insert({
      usuario_id: perfil.usuario_id, brote_id: perfil.brote_whatsapp_defecto, fecha: hoy,
      via_contagio_id: perfil.via_whatsapp_defecto, casos_nuevos: casosNuevos, fallecidos: 0, recuperados: 0,
    }));
  }

  if (error) {
    await registrarLog(perfil.usuario_id, "error", String(error.message));
    return respuestaTwiml("❌ Hubo un error al registrar. Intenta desde la app o contacta soporte.");
  }

  await registrarLog(perfil.usuario_id, "registrado", `+${casosNuevos} casos (total del día: ${totalDia})`);
  return respuestaTwiml(`✅ Registrado. Casos nuevos hoy (${hoy}): ${totalDia} en total.`);
});
