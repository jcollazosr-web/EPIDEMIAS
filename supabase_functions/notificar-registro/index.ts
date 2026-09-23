// notificar-registro -- Llamada internamente por un trigger de la base
// de datos (auth.users, vía pg_net) cada vez que alguien se registra.
// Lee la configuración de Twilio guardada en configuracion_global (con
// el cliente de servicio, que no depende de RLS) y le avisa al admin
// por WhatsApp.
//
// No requiere verificar una firma externa: esta función solo la puede
// invocar la propia base de datos (el trigger), no está pensada para
// recibir tráfico público -- por eso no valida un remitente externo
// como sí hacen bold-webhook o whatsapp-webhook.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });

  let cuerpo: any;
  try {
    cuerpo = await req.json();
  } catch {
    return new Response("JSON inválido", { status: 400 });
  }

  const emailNuevoUsuario = cuerpo.email || "(correo desconocido)";
  const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);

  const leerConfig = async (clave: string): Promise<string | null> => {
    const { data } = await supabase.from("configuracion_global").select("valor").eq("clave", clave).maybeSingle();
    return data?.valor || null;
  };

  const accountSid = await leerConfig("TWILIO_ACCOUNT_SID");
  const authToken = await leerConfig("TWILIO_AUTH_TOKEN");
  const numeroOrigen = await leerConfig("TWILIO_NUMERO_ORIGEN");
  const numeroAdmin = await leerConfig("ADMIN_WHATSAPP_NOTIFICACIONES");

  if (!accountSid || !authToken || !numeroOrigen || !numeroAdmin) {
    // No hay configuración de Twilio todavía -- no es un error grave,
    // simplemente no se envía el aviso (el registro del usuario ya se
    // completó de todas formas, esto es solo una notificación extra).
    return new Response(JSON.stringify({ mensaje: "Twilio no está configurado, no se envió aviso." }), { status: 200 });
  }

  const mensaje = `🆕 Nuevo registro en EpiScan: ${emailNuevoUsuario}\n\nResponde "PRO ${emailNuevoUsuario}" para activarle el plan PRO, o "GRATIS ${emailNuevoUsuario}" para dejarlo en gratis.`;

  const credenciales = btoa(`${accountSid}:${authToken}`);
  const params = new URLSearchParams({
    From: `whatsapp:${numeroOrigen}`,
    To: `whatsapp:${numeroAdmin}`,
    Body: mensaje,
  });

  try {
    const resp = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${accountSid}/Messages.json`, {
      method: "POST",
      headers: {
        "Authorization": `Basic ${credenciales}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: params.toString(),
    });
    const resultado = await resp.text();
    return new Response(JSON.stringify({ mensaje: "Aviso enviado", twilio_status: resp.status, twilio_respuesta: resultado }), { status: 200 });
  } catch (e) {
    return new Response(JSON.stringify({ mensaje: "Error al enviar el aviso", error: String(e) }), { status: 200 });
  }
});
