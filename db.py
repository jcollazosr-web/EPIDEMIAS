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
def get_client() -> Client:
    """
    Cliente de Supabase — UNO POR SESIÓN DE NAVEGADOR, no compartido
    entre usuarios. Antes este cliente vivía en @st.cache_resource
    directamente, lo cual crea UN SOLO objeto para TODO el servidor:
    cuando un usuario cerraba sesión (auth.sign_out()), esa acción
    afectaba al cliente compartido y podía desloguear a otros usuarios
    conectados al mismo proceso, o dejar sesiones "zombie" que fallan
    con 401 en la siguiente operación. Guardarlo en st.session_state
    asegura que cada persona tenga su propia sesión independiente.
    """
    if "_supabase_client" not in st.session_state:
        url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
        key = st.secrets.get("SUPABASE_ANON_KEY", os.environ.get("SUPABASE_ANON_KEY"))
        if not url or not key:
            raise RuntimeError(
                "Faltan SUPABASE_URL / SUPABASE_ANON_KEY. "
                "Defínelas en .streamlit/secrets.toml o como variables de entorno."
            )
        # Se crea un cliente NUEVO por sesión (no se reutiliza el objeto
        # cacheado) para que su estado interno de auth sea 100% propio.
        st.session_state["_supabase_client"] = create_client(url, key)
    return st.session_state["_supabase_client"]


def set_auth_session(access_token: str, refresh_token: str) -> None:
    """Aplica el token de sesión del usuario autenticado al cliente,
    para que las políticas RLS (auth.uid()) funcionen en cada consulta.

    Nota importante (bug real encontrado en producción): el SDK de
    Supabase notifica internamente a su cliente de PostgREST cuando la
    sesión cambia, pero en la práctica esa sincronización puede no
    completarse a tiempo al restaurar una sesión desde una cookie —
    dejando a auth.get_user() funcionando (usa el access_token
    directamente) mientras las consultas a las tablas seguían corriendo
    como anónimo. Por eso, además de set_session(), se fuerza el header
    de autorización de PostgREST explícitamente como medida defensiva.
    """
    client = get_client()
    try:
        client.auth.set_session(access_token, refresh_token)
    except Exception:
        pass
    try:
        client.postgrest.auth(access_token)
    except Exception:
        pass


# ---------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------
def registrar_usuario(email: str, password: str):
    client = get_client()
    return client.auth.sign_up({"email": email, "password": password})


def iniciar_sesion(email: str, password: str):
    client = get_client()
    respuesta = client.auth.sign_in_with_password({"email": email, "password": password})
    # Misma sincronización defensiva que en set_auth_session, por consistencia.
    try:
        if respuesta and respuesta.session:
            client.postgrest.auth(respuesta.session.access_token)
    except Exception:
        pass
    return respuesta


def cerrar_sesion():
    client = get_client()
    try:
        # scope="local": solo cierra ESTA sesión sin revocar el refresh
        # token en el servidor. Nosotros ya limpiamos cookies y
        # session_state por nuestra cuenta; usar "global" aquí no aporta
        # nada (el access_token sigue siendo válido hasta su expiración
        # de todas formas, según el propio SDK) y solo añadía una llamada
        # de red adicional al servidor de auth.
        client.auth.sign_out(options={"scope": "local"})
    except Exception:
        pass


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
    """Trae los brotes que el usuario puede ver: los suyos + los que le
    hayan compartido como colaborador (RLS ya filtra esto solo). Se marca
    cada uno con 'es_dueno' para que la UI distinga qué puede administrar."""
    client = get_client()
    res = client.table("brotes").select("*").order("creado_en").execute()
    brotes = res.data or []
    for b in brotes:
        b["es_dueno"] = (b["usuario_id"] == usuario_id)
    return brotes


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
    """Si el usuario no tiene ningún brote todavía (ni propio ni
    compartido), le crea uno inicial para que la app nunca quede sin un
    brote activo que seleccionar."""
    brotes = listar_brotes(usuario_id)
    if brotes:
        return brotes[0]
    return crear_brote(usuario_id, "Brote 1", "Creado automáticamente")


# ---------------------------------------------------------------------
# Colaboradores por brote
# ---------------------------------------------------------------------
def invitar_colaborador(brote_id: int, correo: str) -> dict:
    client = get_client()
    res = client.rpc("invitar_colaborador", {"p_brote_id": brote_id, "p_correo": correo}).execute()
    return res.data or {}


def listar_colaboradores(brote_id: int) -> list[dict]:
    client = get_client()
    res = client.rpc("listar_colaboradores", {"p_brote_id": brote_id}).execute()
    return res.data or []


def quitar_colaborador(brote_id: int, usuario_id: str) -> None:
    client = get_client()
    client.rpc("quitar_colaborador", {"p_brote_id": brote_id, "p_usuario_id": usuario_id}).execute()


# ---------------------------------------------------------------------
# Dashboard público (enlace compartible de solo lectura, sin login)
# ---------------------------------------------------------------------
def generar_token_publico(brote_id: int) -> str:
    client = get_client()
    res = client.rpc("generar_token_publico", {"p_brote_id": brote_id}).execute()
    return res.data


def revocar_token_publico(brote_id: int) -> None:
    client = get_client()
    client.rpc("revocar_token_publico", {"p_brote_id": brote_id}).execute()


def obtener_brote_publico(token: str) -> dict:
    """No requiere sesión iniciada — la propia función de Postgres valida
    el token y solo devuelve datos de lectura para ESE brote específico."""
    client = get_client()
    res = client.rpc("obtener_brote_publico", {"p_token": token}).execute()
    return res.data or {}


# ---------------------------------------------------------------------
# Historial de cambios (auditoría)
# ---------------------------------------------------------------------
def obtener_historial(brote_id: int, limite: int = 50) -> list[dict]:
    client = get_client()
    res = (
        client.table("historial_cambios")
        .select("*")
        .eq("brote_id", brote_id)
        .order("creado_en", desc=True)
        .limit(limite)
        .execute()
    )
    return res.data or []


# ---------------------------------------------------------------------
# Eventos / marcadores de intervenciones (vacunación, cuarentena, etc.)
# ---------------------------------------------------------------------
def listar_eventos(brote_id: int) -> list[dict]:
    client = get_client()
    res = client.table("eventos_brote").select("*").eq("brote_id", brote_id).order("fecha").execute()
    return res.data or []


def crear_evento(brote_id: int, usuario_id: str, fecha, etiqueta: str) -> dict:
    client = get_client()
    res = client.table("eventos_brote").insert({
        "brote_id": brote_id, "usuario_id": usuario_id,
        "fecha": fecha.isoformat() if hasattr(fecha, "isoformat") else fecha,
        "etiqueta": etiqueta.strip(),
    }).execute()
    return res.data[0] if res.data else {}


def eliminar_evento(evento_id: int) -> None:
    client = get_client()
    client.table("eventos_brote").delete().eq("id", evento_id).execute()


# ---------------------------------------------------------------------
# Fuentes de datos externas configurables (reemplaza el módulo fijo
# anterior de "Datos Abiertos Colombia")
# ---------------------------------------------------------------------
def listar_fuentes_externas(brote_id: int) -> list[dict]:
    client = get_client()
    res = client.table("fuentes_externas_brote").select("*").eq("brote_id", brote_id).order("creado_en").execute()
    return res.data or []


def crear_fuente_externa(brote_id: int, usuario_id: str, nombre: str, tipo: str, configuracion: dict) -> dict:
    client = get_client()
    res = client.table("fuentes_externas_brote").insert({
        "brote_id": brote_id, "usuario_id": usuario_id, "nombre": nombre.strip(),
        "tipo": tipo, "configuracion": configuracion,
    }).execute()
    return res.data[0] if res.data else {}


def eliminar_fuente_externa(fuente_id: int) -> None:
    client = get_client()
    client.table("fuentes_externas_brote").delete().eq("id", fuente_id).execute()


# ---------------------------------------------------------------------
# Vías de contagio
# ---------------------------------------------------------------------
def listar_vias(usuario_id: str) -> list[dict]:
    client = get_client()
    res = client.table("vias_contagio").select("*").eq("usuario_id", usuario_id).order("nombre").execute()
    return res.data or []


def crear_via(usuario_id: str, nombre: str, tipo: str = None) -> dict:
    client = get_client()
    res = client.table("vias_contagio").insert({
        "usuario_id": usuario_id,
        "nombre": nombre.strip(),
        "tipo": tipo,
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
def obtener_registros(usuario_id: str = None, brote_id: Optional[int] = None) -> list[dict]:
    """Trae los registros visibles para la sesión actual (dueño o
    colaborador — lo decide RLS, no este filtro), opcionalmente acotados
    a un solo brote. El parámetro usuario_id ya no se usa para filtrar
    (se deja por compatibilidad de firma) — filtrar por él rompería la
    visibilidad cuando varios colaboradores aportan datos al mismo brote."""
    client = get_client()
    query = client.table("registros_diarios").select(
        "*, vias_contagio(nombre), ubicaciones(pais, departamento, ciudad, barrio, latitud, longitud)"
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


def importar_registros_masivo(usuario_id: str, brote_id: int, filas: list[dict], catalogo_usuario_id: str = None) -> dict:
    """
    Inserta muchos registros de una vez (carga desde Excel/CSV).
    `usuario_id` es quien sube el archivo (autor del registro).
    `catalogo_usuario_id` es el dueño del catálogo de vías/ubicaciones
    (normalmente el dueño del brote) — si no se pasa, se usa usuario_id.
    """
    catalogo_usuario_id = catalogo_usuario_id or usuario_id
    exitosos, fallidos = 0, []
    cache_vias: dict[str, int] = {}

    for i, fila in enumerate(filas):
        try:
            via_nombre = (fila.get("via_nombre") or "").strip()
            via_id = None
            if via_nombre:
                if via_nombre not in cache_vias:
                    existentes = {v["nombre"]: v["id"] for v in listar_vias(catalogo_usuario_id)}
                    if via_nombre not in existentes:
                        crear_via(catalogo_usuario_id, via_nombre)
                        existentes = {v["nombre"]: v["id"] for v in listar_vias(catalogo_usuario_id)}
                    cache_vias[via_nombre] = existentes.get(via_nombre)
                via_id = cache_vias[via_nombre]

            ubicacion_id = None
            ubic = fila.get("ubicacion")
            if ubic and ubic.get("pais"):
                u = obtener_o_crear_ubicacion(
                    catalogo_usuario_id, ubic.get("pais", ""), ubic.get("departamento", ""),
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


def actualizar_registro(registro_id: int, **campos) -> dict:
    """Actualiza un registro existente por su id (para edición desde la
    interfaz — a diferencia de upsert_registro, no depende de que la
    combinación fecha/vía/ubicación se mantenga igual)."""
    client = get_client()
    res = client.table("registros_diarios").update(campos).eq("id", registro_id).execute()
    return res.data[0] if res.data else {}


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


def _geocodificar_inverso(lat: float, lon: float) -> dict:
    """GPS -> país/departamento/ciudad aproximados, usando Nominatim
    (reverse geocoding). Es un "mejor esfuerzo": el usuario siempre puede
    corregir manualmente lo que devuelva antes de guardar."""
    import requests

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1},
            headers={"User-Agent": "SeguimientoEpidemiaApp/1.0"},
            timeout=8,
        )
        datos = resp.json().get("address", {})
        return {
            "pais": datos.get("country", ""),
            "departamento": datos.get("state", ""),
            "ciudad": datos.get("city") or datos.get("town") or datos.get("municipality") or datos.get("village", ""),
            "barrio": datos.get("suburb") or datos.get("neighbourhood", ""),
        }
    except Exception:
        return {"pais": "", "departamento": "", "ciudad": "", "barrio": ""}


def geocodificar_inverso(lat: float, lon: float) -> dict:
    """Wrapper público de _geocodificar_inverso, para usarlo desde la
    interfaz cuando se captura la ubicación por GPS."""
    return _geocodificar_inverso(lat, lon)


def obtener_o_crear_ubicacion(
    usuario_id: str, pais: str, departamento: str = "", ciudad: str = "", barrio: str = "",
    lat_gps: float = None, lon_gps: float = None,
) -> dict:
    """Busca una ubicación existente con esos mismos campos; si no existe,
    la geocodifica y la crea. Evita geocodificar de nuevo algo ya guardado.
    Si se pasan lat_gps/lon_gps (coordenadas reales del GPS del
    dispositivo), se usan tal cual en vez de geocodificar por nombre —
    son más precisas que adivinar la ubicación a partir del texto."""
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

    if lat_gps is not None and lon_gps is not None:
        lat, lon = lat_gps, lon_gps
    else:
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


def eliminar_usuario_admin(usuario_id: str) -> None:
    """Elimina una cuenta por completo (perfil, brotes, registros, todo
    por ON DELETE CASCADE). Solo funciona si quien llama tiene rol admin
    — lo verifica la función de Postgres, no este código."""
    client = get_client()
    client.rpc("admin_eliminar_usuario", {"p_usuario_id": usuario_id}).execute()


# ---------------------------------------------------------------------
# Configuración global (gestionada por el admin, usada por todos)
# ---------------------------------------------------------------------
def obtener_configuracion(clave: str) -> str:
    """Cualquier usuario autenticado puede leer — el valor nunca llega
    al navegador, solo se usa server-side (ej. para llamar a una API)."""
    client = get_client()
    res = client.table("configuracion_global").select("valor").eq("clave", clave).execute()
    return res.data[0]["valor"] if res.data else None


def guardar_configuracion_admin(clave: str, valor: str) -> None:
    """Solo funciona si quien llama tiene rol admin — lo valida la
    función de Postgres, no este código."""
    client = get_client()
    client.rpc("guardar_configuracion_admin", {"p_clave": clave, "p_valor": valor}).execute()
