# -*- coding: utf-8 -*-
"""
correo.py -- Envío de correos a usuarios desde el panel de administrador
(ej. avisos, recordatorios a quienes no han cargado datos, etc.).

Soporta dos proveedores:
- Resend (resend.com): una llamada HTTP simple, pero en su plan gratis
  solo deja enviar a TU PROPIO correo hasta que verifiques un dominio.
- Gmail (SMTP): usa tu propia cuenta de Gmail (con una "contraseña de
  aplicación", no tu contraseña normal) -- gratis, sin necesitar
  dominio propio, con un límite de ~500 correos/día.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

REMITENTE_DEFECTO_RESEND = "EpiScan <onboarding@resend.dev>"


def enviar_correo(destinatario: str, asunto: str, cuerpo_html: str, config: dict) -> dict:
    """
    Punto de entrada único -- despacha al proveedor configurado.
    `config` trae: {'proveedor': 'resend'|'gmail', 'resend_api_key': ...,
    'gmail_direccion': ..., 'gmail_app_password': ...}
    """
    config = config or {}
    proveedor = config.get("proveedor") or "resend"

    if proveedor == "gmail":
        return _enviar_gmail(destinatario, asunto, cuerpo_html, config.get("gmail_direccion"), config.get("gmail_app_password"))
    return _enviar_resend(destinatario, asunto, cuerpo_html, config.get("resend_api_key"))


def _enviar_resend(destinatario: str, asunto: str, cuerpo_html: str, api_key: str, remitente: str = REMITENTE_DEFECTO_RESEND) -> dict:
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


def _enviar_gmail(destinatario: str, asunto: str, cuerpo_html: str, direccion_gmail: str, app_password: str) -> dict:
    if not (direccion_gmail and app_password):
        return {"valido": False, "mensaje": "Falta configurar tu Gmail (dirección o contraseña de aplicación) en el panel de administrador."}

    try:
        mensaje = MIMEMultipart("alternative")
        mensaje["Subject"] = asunto
        mensaje["From"] = direccion_gmail
        mensaje["To"] = destinatario
        mensaje.attach(MIMEText(cuerpo_html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as servidor:
            servidor.starttls()
            servidor.login(direccion_gmail, app_password)
            servidor.sendmail(direccion_gmail, [destinatario], mensaje.as_string())
        return {"valido": True, "mensaje": "Correo enviado."}
    except smtplib.SMTPAuthenticationError:
        return {"valido": False, "mensaje": "Gmail rechazó las credenciales — revisa que sea una 'contraseña de aplicación' de 16 caracteres, no tu contraseña normal de Gmail."}
    except Exception as e:
        return {"valido": False, "mensaje": f"No se pudo enviar por Gmail: {e}"}
