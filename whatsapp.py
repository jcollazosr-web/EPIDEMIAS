# -*- coding: utf-8 -*-
"""
whatsapp.py -- Envío de WhatsApp SALIENTE (ej. avisar al admin cuando
alguien se registra) vía la API de Twilio. Distinto del webhook
whatsapp-webhook (que RECIBE mensajes) -- este módulo solo ENVÍA.
"""
import requests


def enviar_whatsapp(destinatario: str, mensaje: str, account_sid: str, auth_token: str, numero_origen: str) -> dict:
    """Envía un WhatsApp saliente vía la API de Twilio.
    `destinatario` y `numero_origen` deben incluir el indicativo de país
    (ej. '+573001234567'), sin el prefijo 'whatsapp:' -- se agrega aquí."""
    if not (account_sid and auth_token and numero_origen):
        return {"valido": False, "mensaje": "Falta configurar Twilio (Account SID, Auth Token o número de origen) en el panel de administrador."}
    if not destinatario:
        return {"valido": False, "mensaje": "No hay número de destino configurado."}

    try:
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            auth=(account_sid, auth_token),
            data={"From": f"whatsapp:{numero_origen}", "To": f"whatsapp:{destinatario}", "Body": mensaje},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return {"valido": True, "mensaje": "Enviado."}
        return {"valido": False, "mensaje": f"Twilio devolvió un error ({resp.status_code}): {resp.text}"}
    except requests.exceptions.RequestException as e:
        return {"valido": False, "mensaje": f"No se pudo enviar: {e}"}
