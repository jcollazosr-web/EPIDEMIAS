-- =====================================================================
-- ESQUEMA: Sistema de Seguimiento de Epidemia (versión comercial)
-- Base de datos: Supabase (Postgres)
-- Ejecutar esto en: Supabase Dashboard > SQL Editor
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Brotes (permite hacerle seguimiento a varias epidemias en paralelo,
--    en vez de una sola línea de tiempo continua)
-- ---------------------------------------------------------------------
create table if not exists brotes (
    id           bigint generated always as identity primary key,
    usuario_id   uuid references auth.users(id) on delete cascade not null,
    nombre       text not null,
    descripcion  text,
    creado_en    timestamptz default now()
);

alter table brotes enable row level security;

create policy "brotes_solo_propios"
    on brotes
    for all
    using (auth.uid() = usuario_id)
    with check (auth.uid() = usuario_id);

-- ---------------------------------------------------------------------
-- 1. Catálogo de vías de contagio (editable por el usuario desde la app)
-- ---------------------------------------------------------------------
create table if not exists vias_contagio (
    id           bigint generated always as identity primary key,
    usuario_id   uuid references auth.users(id) on delete cascade not null,
    nombre       text not null,
    creado_en    timestamptz default now(),
    unique (usuario_id, nombre)
);

alter table vias_contagio enable row level security;

create policy "vias_solo_propias"
    on vias_contagio
    for all
    using (auth.uid() = usuario_id)
    with check (auth.uid() = usuario_id);

-- ---------------------------------------------------------------------
-- 1b. Catálogo de ubicaciones (país / departamento / ciudad / barrio)
--     Las coordenadas se geocodifican una sola vez (al crear la
--     ubicación) y quedan guardadas — no se vuelve a llamar al servicio
--     de geocodificación en cada consulta.
-- ---------------------------------------------------------------------
create table if not exists ubicaciones (
    id             bigint generated always as identity primary key,
    usuario_id     uuid references auth.users(id) on delete cascade not null,
    pais           text not null,
    departamento   text,
    ciudad         text,
    barrio         text,
    latitud        double precision,
    longitud       double precision,
    creado_en      timestamptz default now(),
    unique (usuario_id, pais, departamento, ciudad, barrio)
);

alter table ubicaciones enable row level security;

create policy "ubicaciones_solo_propias"
    on ubicaciones
    for all
    using (auth.uid() = usuario_id)
    with check (auth.uid() = usuario_id);

-- ---------------------------------------------------------------------
-- 2. Registros diarios (una fila = una fecha + una vía de contagio)
-- ---------------------------------------------------------------------
create table if not exists registros_diarios (
    id              bigint generated always as identity primary key,
    usuario_id      uuid references auth.users(id) on delete cascade not null,
    brote_id        bigint references brotes(id) on delete cascade,
    fecha           date not null,
    via_contagio_id bigint references vias_contagio(id) on delete set null,
    ubicacion_id    bigint references ubicaciones(id) on delete set null,
    casos_nuevos    integer not null check (casos_nuevos >= 0),
    fallecidos      integer not null check (fallecidos >= 0),
    recuperados     integer not null check (recuperados >= 0),
    creado_en       timestamptz default now(),
    actualizado_en  timestamptz default now(),

    -- Un usuario no puede tener dos registros para la misma fecha, vía,
    -- ubicación Y brote (evita duplicados, pero permite el mismo día en
    -- brotes distintos o vías/ubicaciones distintas)
    unique (usuario_id, fecha, via_contagio_id, ubicacion_id, brote_id)
);

create index if not exists idx_registros_brote
    on registros_diarios (brote_id);

create index if not exists idx_registros_usuario_fecha
    on registros_diarios (usuario_id, fecha);

alter table registros_diarios enable row level security;

-- Aislamiento real a nivel de base de datos: aunque haya un bug en el
-- código de la app, Postgres nunca deja que un usuario vea/edite/borre
-- registros de otro usuario.
create policy "registros_solo_propios_select"
    on registros_diarios
    for select
    using (auth.uid() = usuario_id);

create policy "registros_solo_propios_insert"
    on registros_diarios
    for insert
    with check (auth.uid() = usuario_id);

create policy "registros_solo_propios_update"
    on registros_diarios
    for update
    using (auth.uid() = usuario_id)
    with check (auth.uid() = usuario_id);

create policy "registros_solo_propios_delete"
    on registros_diarios
    for delete
    using (auth.uid() = usuario_id);

-- ---------------------------------------------------------------------
-- 3. Trigger para actualizar "actualizado_en" automáticamente
-- ---------------------------------------------------------------------
create or replace function set_actualizado_en()
returns trigger as $$
begin
    new.actualizado_en = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_actualizado_en on registros_diarios;
create trigger trg_actualizado_en
    before update on registros_diarios
    for each row
    execute function set_actualizado_en();

-- ---------------------------------------------------------------------
-- NOTA DE MIGRACIÓN: si ya habías ejecutado una versión anterior de este
-- esquema (sin ubicaciones), ejecuta esto en vez de recrear todo desde
-- cero, para no perder los registros ya guardados:
--
--   create table if not exists ubicaciones (...)   -- ver bloque 1b arriba
--   alter table registros_diarios add column if not exists ubicacion_id bigint references ubicaciones(id) on delete set null;
--   alter table registros_diarios drop constraint if exists registros_diarios_usuario_id_fecha_via_contagio_id_key;
--   alter table registros_diarios add constraint registros_diarios_usuario_id_fecha_via_contagio_id_ubicacion_id_key unique (usuario_id, fecha, via_contagio_id, ubicacion_id);
-- ---------------------------------------------------------------------

-- ---------------------------------------------------------------------
-- 5. Perfil opcional (nombre visible, organización) — no obligatorio
--    para el funcionamiento, pero útil para reportes/exportes.
-- ---------------------------------------------------------------------
create table if not exists perfiles (
    usuario_id      uuid references auth.users(id) on delete cascade primary key,
    nombre_completo text,
    organizacion    text,
    rol             text not null default 'usuario' check (rol in ('usuario', 'admin')),
    creado_en       timestamptz default now()
);

alter table perfiles enable row level security;

create policy "perfil_solo_propio"
    on perfiles
    for all
    using (auth.uid() = usuario_id)
    with check (auth.uid() = usuario_id);

-- Defensa en profundidad: aunque la política de arriba permite al usuario
-- actualizar su propia fila, esta función evita que pueda auto-asignarse
-- el rol 'admin' a través de una llamada UPDATE directa. Solo un cliente
-- con la service_role key (que bypasea RLS) puede cambiar el rol —
-- eso es exactamente lo que hará el panel de administrador desde el
-- backend, nunca el usuario final desde su propia sesión.
create or replace function evitar_autoasignacion_de_rol()
returns trigger as $$
begin
    if new.rol is distinct from old.rol and auth.role() <> 'service_role' then
        new.rol := old.rol;
    end if;
    return new;
end;
$$ language plpgsql security definer;

drop trigger if exists trg_evitar_autoasignacion_rol on perfiles;
create trigger trg_evitar_autoasignacion_rol
    before update on perfiles
    for each row
    execute function evitar_autoasignacion_de_rol();

-- Crea automáticamente una fila de perfil vacía cuando alguien se registra
create or replace function crear_perfil_para_nuevo_usuario()
returns trigger as $$
begin
    insert into public.perfiles (usuario_id) values (new.id);
    return new;
end;
$$ language plpgsql security definer;

drop trigger if exists trg_crear_perfil on auth.users;
create trigger trg_crear_perfil
    after insert on auth.users
    for each row
    execute function crear_perfil_para_nuevo_usuario();

-- ---------------------------------------------------------------------
-- IMPORTANTE: para crear tu primer usuario administrador, regístrate
-- normalmente desde la app y luego ejecuta esto UNA vez en el SQL Editor
-- de Supabase, reemplazando el correo por el tuyo:
--
--   update perfiles set rol = 'admin'
--   where usuario_id = (select id from auth.users where email = 'tu-correo@ejemplo.com');
--
-- El SQL Editor de Supabase corre con privilegios que sí pueden cambiar
-- el rol (no pasa por RLS ni por el trigger de arriba de la misma forma
-- que un usuario final).
-- ---------------------------------------------------------------------

-- ---------------------------------------------------------------------
-- 6. Funciones del panel de administrador (sin usar service_role key)
--
-- Estas funciones corren con privilegios elevados (SECURITY DEFINER)
-- pero verifican INTERNAMENTE que quien llama tiene rol 'admin' antes
-- de devolver nada. Así el panel de administrador funciona con la
-- clave pública (anon), sin necesidad de exponer nunca la service_role
-- key dentro de la app.
-- ---------------------------------------------------------------------
create or replace function admin_estadisticas_globales()
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
    es_admin boolean;
    resultado json;
begin
    select (rol = 'admin') into es_admin from perfiles where usuario_id = auth.uid();
    if not coalesce(es_admin, false) then
        raise exception 'No autorizado: se requiere rol admin';
    end if;

    select json_build_object(
        'total_usuarios_registrados', (select count(*) from perfiles),
        'usuarios_con_al_menos_un_registro', (select count(distinct usuario_id) from registros_diarios),
        'usuarios_activos_ultimos_7_dias', (select count(distinct usuario_id) from registros_diarios where fecha >= current_date - interval '7 days'),
        'total_registros_capturados', (select count(*) from registros_diarios),
        'total_casos_nuevos_acumulados', (select coalesce(sum(casos_nuevos),0) from registros_diarios),
        'total_fallecidos_acumulados', (select coalesce(sum(fallecidos),0) from registros_diarios)
    ) into resultado;

    return resultado;
end;
$$;

grant execute on function admin_estadisticas_globales() to authenticated;

create or replace function admin_listar_usuarios()
returns table(email text, creado_en timestamptz, confirmado boolean)
language plpgsql
security definer
set search_path = public, auth
as $$
begin
    if not exists (select 1 from perfiles where usuario_id = auth.uid() and rol = 'admin') then
        raise exception 'No autorizado: se requiere rol admin';
    end if;

    return query
    select u.email::text, u.created_at, (u.email_confirmed_at is not null)
    from auth.users u
    order by u.created_at;
end;
$$;

grant execute on function admin_listar_usuarios() to authenticated;
