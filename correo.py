# -*- coding: utf-8 -*-
"""
correo.py -- Envío de correos a usuarios desde el panel de administrador
(ej. avisos, recordatorios a quienes no han cargado datos, etc.).

Usa Resend (resend.com) -- una sola llamada HTTP, sin necesidad de
servidor propio ni de exponer credenciales SMTP. Tiene un plan gratis
generoso (3.000 correos/mes, 100/día) que cubre holgadamente el volumen
de usuarios actual de la app.
"""
import requests

REMITENTE_DEFECTO = "EpiScan <onboarding@resend.dev>"


def enviar_correo(destinatario: str, asunto: str, cuerpo_html: str, api_key: str, remitente: str = REMITENTE_DEFECTO) -> dict:
    """Envía un correo vía la API de Resend. Devuelve
    {'valido': True/False, 'mensaje': ...}."""
    if not api_key:
        return {"valido": False, "mensaje": "El administrador todavía no ha configurado la clave de Resend."}

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": remitente, "to": [destinatario], "subject": asunto, "html": cuerpo_html},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return {"valido": True, "mensaje": "Correo enviado."}
        return {"valido": False, "mensaje": f"Resend devolvió un error ({resp.status_code}): {resp.text}"}
    except requests.exceptions.RequestException as e:
        return {"valido": False, "mensaje": f"No se pudo enviar el correo: {e}"}
