# -*- coding: utf-8 -*-
"""
sso.py — Ingreso único desde la Historia Clínica Electrónica (HCE).

La HCE abre EpiScan con ?sso=<pase firmado>. Aquí se envía el pase a la
función de Supabase «sso-hce», que verifica la firma, crea la cuenta si
hace falta y devuelve un token_hash de un solo uso. Ese token se canjea
con verify_otp para abrir la sesión del usuario (con RLS normal): la
service_role key nunca pasa por esta app.
"""
import os

import requests
import streamlit as st

import db


def _config():
    url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    key = st.secrets.get("SUPABASE_ANON_KEY", os.environ.get("SUPABASE_ANON_KEY"))
    return url, key


def ingresar(pase: str) -> tuple[dict | None, str]:
    """Devuelve ({"id", "email"}, "") si el pase es válido; (None, motivo) si no."""
    url, key = _config()
    if not url or not key or not pase:
        return None, "Falta la configuración de Supabase."
    try:
        r = requests.post(f"{url.rstrip('/')}/functions/v1/sso-hce", json={"token": pase[:4000]},
                          headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=25)
        datos = r.json() if r.content else {}
    except Exception:
        return None, "No se pudo validar el ingreso desde la historia clínica."
    if r.status_code != 200 or not datos.get("token_hash"):
        return None, datos.get("error") or "No se pudo validar el ingreso desde la historia clínica."
    client = db.get_client()
    respuesta = None
    for tipo in ("magiclink", "email"):
        try:
            respuesta = client.auth.verify_otp({"token_hash": datos["token_hash"], "type": tipo})
            if respuesta and respuesta.session:
                break
        except Exception:
            respuesta = None
    if not respuesta or not respuesta.session:
        return None, "No se pudo abrir la sesión de EpiScan."
    db.set_auth_session(respuesta.session.access_token, respuesta.session.refresh_token)
    return {"id": respuesta.user.id, "email": respuesta.user.email,
            "_tokens": (respuesta.session.access_token, respuesta.session.refresh_token)}, ""
