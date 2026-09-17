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


def set_auth_session(access_token: str, refresh_token: str) -> None:
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


def cambiar_password(nueva_password: str):
    """Cambia la contraseña del usuario ya autenticado en esta sesión."""
    client = get_client()
    return client.auth.update_user({"password": nueva_password})


# ---------------------------------------------------------------------
# Brotes (permite hacerle seguimiento a varias epidemias en paralelo)
# ---------------------------------------------------------------------
def listar_brotes(usuario_id: str) -> list[dict]:
    client = get_client()
    res = client.table("brotes").select("*").eq("usuario_id", usuario_id).order("creado_en").execute()
    return res.data or []


def crear_brote(usuario_id: str, nombre: str, descripcion: str = "") -> dict:
    client = get_client()
    res = client.table("brotes").insert({
        "usuario_id": usuario_id, "nombre": nombre.strip(), "descripcion": descripcion.strip() or None,
    }).execute()
    return res.data[0] if res.data else {}


def eliminar_brote(brote_id: int) -> None:
    """Elimina el brote Y todos sus registros (por ON DELETE CASCADE)."""
    client = get_client()
    client.table("brotes").delete().eq("id", brote_id).execute()


def asegurar_brote_por_defecto(usuario_id: str) -> dict:
    """Si el usuario no tiene ningún brote todavía, le crea uno inicial
    para que la app nunca quede sin un brote activo que seleccionar."""
    brotes = listar_brotes(usuario_id)
    if brotes:
        return brotes[0]
    return crear_brote(usuario_id, "Brote 1", "Creado automáticamente")


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
def obtener_registros(usuario_id: str, brote_id: Optional[int] = None) -> list[dict]:
    """Trae los registros del usuario (opcionalmente filtrados a un solo
    brote), con el nombre de la vía y la ubicación ya resueltos (join)."""
    client = get_client()
    query = (
        client.table("registros_diarios")
        .select("*, vias_contagio(nombre), ubicaciones(pais, departamento, ciudad, barrio, latitud, longitud)")
        .eq("usuario_id", usuario_id)
    )
    if brote_id is not None:
        query = query.eq("brote_id", brote_id)
    res = query.order("fecha").execute()
    return res.data or []


def obtener_registros_ultimos_n_dias(usuario_id: str, brote_id: Optional[int] = None, n_dias: int = 15) -> list[dict]:
    """Ventana móvil de entrenamiento: últimos N días con datos,
    usada por los modelos convencionales (regresión, SIR, etc.)."""
    todos = obtener_registros(usuario_id, brote_id=brote_id)
    fechas_unicas = sorted({r["fecha"] for r in todos}, reverse=True)[:n_dias]
    return [r for r in todos if r["fecha"] in fechas_unicas]


def upsert_registro(
    usuario_id: str,
    brote_id: int,
    fecha: date,
    via_contagio_id: Optional[int],
    casos_nuevos: int,
    fallecidos: int,
    recuperados: int,
    ubicacion_id: Optional[int] = None,
) -> dict:
    """Inserta o actualiza (según la restricción UNIQUE fecha+vía+ubicación+brote)
    el registro de un día para un brote, vía de contagio y ubicación específicos."""
    client = get_client()
    payload = {
        "usuario_id": usuario_id,
        "brote_id": brote_id,
        "fecha": fecha.isoformat(),
        "via_contagio_id": via_contagio_id,
        "ubicacion_id": ubicacion_id,
        "casos_nuevos": casos_nuevos,
        "fallecidos": fallecidos,
        "recuperados": recuperados,
    }
    res = (
        client.table("registros_diarios")
        .upsert(payload, on_conflict="usuario_id,fecha,via_contagio_id,ubicacion_id,brote_id")
        .execute()
    )
    return res.data[0] if res.data else {}


def importar_registros_masivo(usuario_id: str, brote_id: int, filas: list[dict]) -> dict:
    """
    Inserta muchos registros de una vez (carga desde Excel/CSV).
    Cada fila en `filas` debe traer: fecha (date), via_nombre (str, opcional),
    ubicacion (dict opcional con pais/departamento/ciudad/barrio),
    casos_nuevos, fallecidos, recuperados.

    Reutiliza/crea vías y ubicaciones automáticamente por nombre, igual que
    el formulario manual, para no duplicar catálogos.
    """
    exitosos, fallidos = 0, []
    cache_vias: dict[str, int] = {}

    for i, fila in enumerate(filas):
        try:
            via_nombre = (fila.get("via_nombre") or "").strip()
            via_id = None
            if via_nombre:
                if via_nombre not in cache_vias:
                    existentes = {v["nombre"]: v["id"] for v in listar_vias(usuario_id)}
                    if via_nombre not in existentes:
                        crear_via(usuario_id, via_nombre)
                        existentes = {v["nombre"]: v["id"] for v in listar_vias(usuario_id)}
                    cache_vias[via_nombre] = existentes.get(via_nombre)
                via_id = cache_vias[via_nombre]

            ubicacion_id = None
            ubic = fila.get("ubicacion")
            if ubic and ubic.get("pais"):
                u = obtener_o_crear_ubicacion(
                    usuario_id, ubic.get("pais", ""), ubic.get("departamento", ""),
                    ubic.get("ciudad", ""), ubic.get("barrio", ""),
                )
                ubicacion_id = u.get("id")

            upsert_registro(
                usuario_id=usuario_id,
                brote_id=brote_id,
                fecha=fila["fecha"],
                via_contagio_id=via_id,
                ubicacion_id=ubicacion_id,
                casos_nuevos=int(fila.get("casos_nuevos", 0)),
                fallecidos=int(fila.get("fallecidos", 0)),
                recuperados=int(fila.get("recuperados", 0)),
            )
            exitosos += 1
        except Exception as e:
            fallidos.append({"fila": i + 1, "error": str(e)})

    return {"exitosos": exitosos, "fallidos": fallidos}


def eliminar_registro(registro_id: int) -> None:
    client = get_client()
    client.table("registros_diarios").delete().eq("id", registro_id).execute()


def contar_registros_totales(usuario_id: str, brote_id: Optional[int] = None) -> int:
    return len(obtener_registros(usuario_id, brote_id=brote_id))


def contar_registros_por_via(usuario_id: str, brote_id: Optional[int] = None) -> dict[str, int]:
    registros = obtener_registros(usuario_id, brote_id=brote_id)
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
# Panel de administrador (requiere rol == 'admin').
#
# En vez de una service_role key (que anula RLS por completo y sería
# riesgoso exponer en la app), usamos funciones de Postgres que
# verifican el rol INTERNAMENTE (ver admin_estadisticas_globales y
# admin_listar_usuarios en schema.sql). El cliente normal (anon) puede
# llamarlas porque Postgres, no el código de la app, hace el chequeo.
# ---------------------------------------------------------------------
def estadisticas_globales_admin() -> dict:
    """Llama a la función admin_estadisticas_globales() vía RPC.
    Si el usuario no tiene rol admin, Postgres rechaza la llamada."""
    client = get_client()
    res = client.rpc("admin_estadisticas_globales", {}).execute()
    return res.data or {}


def listar_usuarios_admin() -> list[dict]:
    """Llama a la función admin_listar_usuarios() vía RPC."""
    client = get_client()
    res = client.rpc("admin_listar_usuarios", {}).execute()
    return res.data or []
