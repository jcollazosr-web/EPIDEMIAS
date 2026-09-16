# -*- coding: utf-8 -*-
"""
db.py — Capa de acceso a datos (Supabase).

Toda la lógica de lectura/escritura contra Postgres vive aquí, separada
de la interfaz de Streamlit, para poder testear y reemplazar el backend
sin tocar la UI.
"""
import os
from datetime import date
from typing import Optional

import streamlit as st
from supabase import create_client, Client


# ---------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------
@st.cache_resource
def get_client() -> Client:
    """
    Crea (una sola vez por proceso) el cliente de Supabase.
    Las credenciales se leen de variables de entorno o de
    st.secrets (recomendado en Streamlit Cloud).
    """
    url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    key = st.secrets.get("SUPABASE_ANON_KEY", os.environ.get("SUPABASE_ANON_KEY"))
    if not url or not key:
        raise RuntimeError(
            "Faltan SUPABASE_URL / SUPABASE_ANON_KEY. "
            "Defínelas en .streamlit/secrets.toml o como variables de entorno."
        )
    return create_client(url, key)


@st.cache_resource
def get_admin_client() -> Client:
    """
    Cliente con la SERVICE ROLE KEY de Supabase: bypasea RLS por completo.
    Úsalo ÚNICAMENTE detrás de una verificación de rol == 'admin' hecha
    con el cliente normal (que sí respeta RLS). Nunca expongas esta key
    al navegador — en Streamlit es seguro guardarla en st.secrets porque
    la app corre del lado del servidor, pero nunca la imprimas en pantalla
    ni la subas a un repositorio.
    """
    url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    service_key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not service_key:
        raise RuntimeError(
            "Falta SUPABASE_SERVICE_ROLE_KEY. Solo es necesaria para el panel "
            "de administrador — no se requiere para el uso normal de la app."
        )
    return create_client(url, service_key)
    """Aplica el token de sesión del usuario autenticado al cliente,
    para que las políticas RLS (auth.uid()) funcionen en cada consulta."""
    client = get_client()
    client.auth.set_session(access_token, refresh_token)


# ---------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------
def registrar_usuario(email: str, password: str):
    client = get_client()
    return client.auth.sign_up({"email": email, "password": password})


def iniciar_sesion(email: str, password: str):
    client = get_client()
    return client.auth.sign_in_with_password({"email": email, "password": password})


def cerrar_sesion():
    client = get_client()
    client.auth.sign_out()


def obtener_perfil(usuario_id: str) -> dict:
    """Perfil del usuario autenticado (respeta RLS: solo trae su propia fila)."""
    client = get_client()
    res = client.table("perfiles").select("*").eq("usuario_id", usuario_id).execute()
    return res.data[0] if res.data else {}


def es_admin(usuario_id: str) -> bool:
    perfil = obtener_perfil(usuario_id)
    return perfil.get("rol") == "admin"


def recuperar_password(email: str):
    client = get_client()
    return client.auth.reset_password_for_email(email)


# ---------------------------------------------------------------------
# Vías de contagio
# ---------------------------------------------------------------------
def listar_vias(usuario_id: str) -> list[dict]:
    client = get_client()
    res = client.table("vias_contagio").select("*").eq("usuario_id", usuario_id).order("nombre").execute()
    return res.data or []


def crear_via(usuario_id: str, nombre: str) -> dict:
    client = get_client()
    res = client.table("vias_contagio").insert({
        "usuario_id": usuario_id,
        "nombre": nombre.strip(),
    }).execute()
    return res.data[0] if res.data else {}


def asegurar_vias_por_defecto(usuario_id: str) -> None:
    """La primera vez que un usuario entra, le crea un catálogo base
    de vías de contagio si aún no tiene ninguna."""
    existentes = listar_vias(usuario_id)
    if existentes:
        return
    vias_base = ["Contacto directo", "Gotículas / respiratoria", "Fómites", "Vectorial", "Desconocida"]
    for nombre in vias_base:
        try:
            crear_via(usuario_id, nombre)
        except Exception:
            # Si ya existe (choque de índice único), seguimos sin romper
            pass


# ---------------------------------------------------------------------
# Registros diarios
# ---------------------------------------------------------------------
def obtener_registros(usuario_id: str) -> list[dict]:
    """Trae todos los registros del usuario, con el nombre de la vía
    y la ubicación ya resueltos (join), ordenados por fecha."""
    client = get_client()
    res = (
        client.table("registros_diarios")
        .select("*, vias_contagio(nombre), ubicaciones(pais, departamento, ciudad, barrio, latitud, longitud)")
        .eq("usuario_id", usuario_id)
        .order("fecha")
        .execute()
    )
    return res.data or []


def obtener_registros_ultimos_n_dias(usuario_id: str, n_dias: int = 15) -> list[dict]:
    """Ventana móvil de entrenamiento: últimos N días con datos,
    usada por los modelos convencionales (regresión, SIR, etc.)."""
    todos = obtener_registros(usuario_id)
    fechas_unicas = sorted({r["fecha"] for r in todos}, reverse=True)[:n_dias]
    return [r for r in todos if r["fecha"] in fechas_unicas]


def upsert_registro(
    usuario_id: str,
    fecha: date,
    via_contagio_id: Optional[int],
    casos_nuevos: int,
    fallecidos: int,
    recuperados: int,
    ubicacion_id: Optional[int] = None,
) -> dict:
    """Inserta o actualiza (según la restricción UNIQUE fecha+vía+ubicación)
    el registro de un día para una vía de contagio y ubicación específicas."""
    client = get_client()
    payload = {
        "usuario_id": usuario_id,
        "fecha": fecha.isoformat(),
        "via_contagio_id": via_contagio_id,
        "ubicacion_id": ubicacion_id,
        "casos_nuevos": casos_nuevos,
        "fallecidos": fallecidos,
        "recuperados": recuperados,
    }
    res = (
        client.table("registros_diarios")
        .upsert(payload, on_conflict="usuario_id,fecha,via_contagio_id,ubicacion_id")
        .execute()
    )
    return res.data[0] if res.data else {}


def eliminar_registro(registro_id: int) -> None:
    client = get_client()
    client.table("registros_diarios").delete().eq("id", registro_id).execute()


def contar_registros_totales(usuario_id: str) -> int:
    return len(obtener_registros(usuario_id))


def contar_registros_por_via(usuario_id: str) -> dict[str, int]:
    registros = obtener_registros(usuario_id)
    conteo: dict[str, int] = {}
    for r in registros:
        nombre_via = (r.get("vias_contagio") or {}).get("nombre", "Sin vía")
        conteo[nombre_via] = conteo.get(nombre_via, 0) + 1
    return conteo


# ---------------------------------------------------------------------
# Ubicaciones (país / departamento / ciudad / barrio) + geocodificación
# ---------------------------------------------------------------------
def listar_ubicaciones(usuario_id: str) -> list[dict]:
    client = get_client()
    res = (
        client.table("ubicaciones")
        .select("*")
        .eq("usuario_id", usuario_id)
        .order("pais")
        .execute()
    )
    return res.data or []


def _geocodificar(pais: str, departamento: str, ciudad: str, barrio: str) -> tuple[Optional[float], Optional[float]]:
    """
    Geocodifica una dirección usando Nominatim (OpenStreetMap), gratuito.
    Se llama UNA sola vez por ubicación nueva (el resultado queda guardado
    en la tabla `ubicaciones`), respetando el límite de 1 solicitud/segundo
    de la política de uso de Nominatim.

    Si la geocodificación falla (barrio muy específico sin cobertura,
    error de red, etc.), devuelve (None, None) — la ubicación se guarda
    igual, y el usuario puede editar las coordenadas manualmente después
    si lo necesita.
    """
    import requests

    partes = [p for p in [barrio, ciudad, departamento, pais] if p and p.strip()]
    consulta = ", ".join(partes)

    try:
        respuesta = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": consulta, "format": "json", "limit": 1},
            headers={"User-Agent": "SeguimientoEpidemiaApp/1.0"},
            timeout=8,
        )
        resultados = respuesta.json()
        if resultados:
            return float(resultados[0]["lat"]), float(resultados[0]["lon"])
    except Exception:
        pass

    # Si el barrio específico no se encuentra, se intenta con menos detalle
    # (ciudad + país) para al menos ubicar la zona aproximada.
    if barrio:
        return _geocodificar(pais, departamento, ciudad, "")
    return None, None


def obtener_o_crear_ubicacion(
    usuario_id: str, pais: str, departamento: str = "", ciudad: str = "", barrio: str = ""
) -> dict:
    """Busca una ubicación existente con esos mismos campos; si no existe,
    la geocodifica y la crea. Evita geocodificar de nuevo algo ya guardado."""
    client = get_client()

    consulta = (
        client.table("ubicaciones")
        .select("*")
        .eq("usuario_id", usuario_id)
        .eq("pais", pais)
        .eq("departamento", departamento or "")
        .eq("ciudad", ciudad or "")
        .eq("barrio", barrio or "")
        .execute()
    )
    if consulta.data:
        return consulta.data[0]

    lat, lon = _geocodificar(pais, departamento, ciudad, barrio)
    res = client.table("ubicaciones").insert({
        "usuario_id": usuario_id,
        "pais": pais,
        "departamento": departamento or None,
        "ciudad": ciudad or None,
        "barrio": barrio or None,
        "latitud": lat,
        "longitud": lon,
    }).execute()
    return res.data[0] if res.data else {}


# ---------------------------------------------------------------------
# Panel de administrador (requiere rol == 'admin', verificado ANTES de
# usar el cliente con service role key)
# ---------------------------------------------------------------------
def estadisticas_globales_admin() -> dict:
    """
    Estadísticas agregadas de TODA la app (todos los usuarios).
    Usa el cliente con service_role key porque RLS bloquea intencionalmente
    ver datos de otros usuarios con el cliente normal. Llamar SOLO después
    de confirmar es_admin(usuario_id_actual) con el cliente normal.
    """
    admin = get_admin_client()

    perfiles = admin.table("perfiles").select("usuario_id", count="exact").execute()
    total_usuarios = perfiles.count if perfiles.count is not None else len(perfiles.data or [])

    registros = admin.table("registros_diarios").select(
        "usuario_id, fecha, casos_nuevos, fallecidos, recuperados"
    ).execute().data or []

    total_casos = sum(r["casos_nuevos"] for r in registros)
    total_fallecidos = sum(r["fallecidos"] for r in registros)
    usuarios_con_datos = len({r["usuario_id"] for r in registros})

    from datetime import date, timedelta
    hace_7_dias = (date.today() - timedelta(days=7)).isoformat()
    usuarios_activos_7d = len({r["usuario_id"] for r in registros if str(r["fecha"]) >= hace_7_dias})

    return {
        "total_usuarios_registrados": total_usuarios,
        "usuarios_con_al_menos_un_registro": usuarios_con_datos,
        "usuarios_activos_ultimos_7_dias": usuarios_activos_7d,
        "total_registros_capturados": len(registros),
        "total_casos_nuevos_acumulados": total_casos,
        "total_fallecidos_acumulados": total_fallecidos,
    }


def listar_usuarios_admin() -> list[dict]:
    """Lista básica de usuarios (correo, fecha de registro, rol) para el
    panel de administrador. Requiere la Admin API de Supabase Auth."""
    admin = get_admin_client()
    resultado = admin.auth.admin.list_users()
    usuarios = []
    for u in resultado:
        usuarios.append({
            "email": u.email,
            "creado_en": u.created_at,
            "confirmado": u.email_confirmed_at is not None,
        })
    return usuarios
