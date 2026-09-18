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


-- =========================================================================
-- MIGRACIÓN: Colaboradores por brote + Auditoría de cambios
-- =========================================================================
create table if not exists colaboradores_brote (
    id           bigint generated always as identity primary key,
    brote_id     bigint references brotes(id) on delete cascade not null,
    usuario_id   uuid references auth.users(id) on delete cascade not null,
    invitado_por uuid references auth.users(id),
    creado_en    timestamptz default now(),
    unique (brote_id, usuario_id)
);

alter table colaboradores_brote enable row level security;

-- IMPORTANTE: esta política NO debe volver a referenciar la tabla
-- `brotes` (causaría recursión infinita, ya que la política de brotes
-- referencia esta tabla). Para que el dueño vea/gestione la lista
-- completa de colaboradores, se usan las funciones de abajo.
create policy "colaboradores_select_propio"
    on colaboradores_brote for select
    using (usuario_id = auth.uid());

create or replace function listar_colaboradores(p_brote_id bigint)
returns table(usuario_id uuid, email text, creado_en timestamptz)
language plpgsql security definer set search_path = public, auth
as $$
begin
    if not exists (select 1 from brotes b where b.id = p_brote_id and b.usuario_id = auth.uid()) then
        raise exception 'Solo el dueño del brote puede ver sus colaboradores';
    end if;
    return query
    select c.usuario_id, u.email::text, c.creado_en
    from colaboradores_brote c join auth.users u on u.id = c.usuario_id
    where c.brote_id = p_brote_id order by c.creado_en;
end;
$$;
grant execute on function listar_colaboradores(bigint) to authenticated;

create or replace function quitar_colaborador(p_brote_id bigint, p_usuario_id uuid)
returns void language plpgsql security definer as $$
begin
    if not exists (select 1 from brotes b where b.id = p_brote_id and b.usuario_id = auth.uid()) then
        raise exception 'Solo el dueño del brote puede quitar colaboradores';
    end if;
    delete from colaboradores_brote where brote_id = p_brote_id and usuario_id = p_usuario_id;
end;
$$;
grant execute on function quitar_colaborador(bigint, uuid) to authenticated;

create or replace function invitar_colaborador(p_brote_id bigint, p_correo text)
returns json language plpgsql security definer set search_path = public, auth as $$
declare
    v_usuario_destino uuid;
begin
    if not exists (select 1 from brotes b where b.id = p_brote_id and b.usuario_id = auth.uid()) then
        raise exception 'Solo el dueño del brote puede invitar colaboradores';
    end if;
    select u.id into v_usuario_destino from auth.users u where u.email = p_correo;
    if v_usuario_destino is null then
        raise exception 'No existe ningún usuario registrado con ese correo';
    end if;
    if v_usuario_destino = auth.uid() then
        raise exception 'No puedes invitarte a ti mismo';
    end if;
    insert into colaboradores_brote (brote_id, usuario_id, invitado_por)
    values (p_brote_id, v_usuario_destino, auth.uid())
    on conflict (brote_id, usuario_id) do nothing;
    return json_build_object('exito', true);
end;
$$;
grant execute on function invitar_colaborador(bigint, text) to authenticated;

-- Ampliar RLS de brotes/registros/vías/ubicaciones para colaboradores
drop policy if exists "brotes_solo_propios" on brotes;
create policy "brotes_select_dueno_o_colaborador" on brotes for select
    using (auth.uid() = usuario_id or exists (select 1 from colaboradores_brote c where c.brote_id = brotes.id and c.usuario_id = auth.uid()));
create policy "brotes_insert_propio" on brotes for insert with check (auth.uid() = usuario_id);
create policy "brotes_update_propio" on brotes for update using (auth.uid() = usuario_id) with check (auth.uid() = usuario_id);
create policy "brotes_delete_propio" on brotes for delete using (auth.uid() = usuario_id);

drop policy if exists "registros_solo_propios_select" on registros_diarios;
drop policy if exists "registros_solo_propios_insert" on registros_diarios;
drop policy if exists "registros_solo_propios_update" on registros_diarios;
drop policy if exists "registros_solo_propios_delete" on registros_diarios;

create policy "registros_select_acceso_brote" on registros_diarios for select
    using (exists (select 1 from brotes b where b.id = registros_diarios.brote_id
        and (b.usuario_id = auth.uid() or exists (select 1 from colaboradores_brote c where c.brote_id = b.id and c.usuario_id = auth.uid()))));
create policy "registros_insert_acceso_brote" on registros_diarios for insert
    with check (exists (select 1 from brotes b where b.id = registros_diarios.brote_id
        and (b.usuario_id = auth.uid() or exists (select 1 from colaboradores_brote c where c.brote_id = b.id and c.usuario_id = auth.uid()))));
create policy "registros_update_acceso_brote" on registros_diarios for update
    using (exists (select 1 from brotes b where b.id = registros_diarios.brote_id
        and (b.usuario_id = auth.uid() or exists (select 1 from colaboradores_brote c where c.brote_id = b.id and c.usuario_id = auth.uid()))))
    with check (exists (select 1 from brotes b where b.id = registros_diarios.brote_id
        and (b.usuario_id = auth.uid() or exists (select 1 from colaboradores_brote c where c.brote_id = b.id and c.usuario_id = auth.uid()))));
create policy "registros_delete_acceso_brote" on registros_diarios for delete
    using (exists (select 1 from brotes b where b.id = registros_diarios.brote_id
        and (b.usuario_id = auth.uid() or exists (select 1 from colaboradores_brote c where c.brote_id = b.id and c.usuario_id = auth.uid()))));

drop policy if exists "vias_solo_propias" on vias_contagio;
create policy "vias_select_autenticados" on vias_contagio for select using (auth.role() = 'authenticated');
create policy "vias_insert_propio" on vias_contagio for insert with check (auth.uid() = usuario_id);
create policy "vias_update_propio" on vias_contagio for update using (auth.uid() = usuario_id) with check (auth.uid() = usuario_id);
create policy "vias_delete_propio" on vias_contagio for delete using (auth.uid() = usuario_id);

drop policy if exists "ubicaciones_solo_propias" on ubicaciones;
create policy "ubicaciones_select_autenticados" on ubicaciones for select using (auth.role() = 'authenticated');
create policy "ubicaciones_insert_propio" on ubicaciones for insert with check (auth.uid() = usuario_id);
create policy "ubicaciones_update_propio" on ubicaciones for update using (auth.uid() = usuario_id) with check (auth.uid() = usuario_id);
create policy "ubicaciones_delete_propio" on ubicaciones for delete using (auth.uid() = usuario_id);

-- Auditoría
create table if not exists historial_cambios (
    id           bigint generated always as identity primary key,
    brote_id     bigint references brotes(id) on delete cascade,
    usuario_id   uuid references auth.users(id),
    accion       text not null check (accion in ('crear','actualizar','eliminar')),
    registro_id  bigint,
    detalle      jsonb,
    creado_en    timestamptz default now()
);
alter table historial_cambios enable row level security;
create policy "historial_select_acceso_brote" on historial_cambios for select
    using (exists (select 1 from brotes b where b.id = historial_cambios.brote_id
        and (b.usuario_id = auth.uid() or exists (select 1 from colaboradores_brote c where c.brote_id = b.id and c.usuario_id = auth.uid()))));

create or replace function registrar_historial_registro() returns trigger
language plpgsql security definer as $$
begin
    if (tg_op = 'INSERT') then
        insert into historial_cambios (brote_id, usuario_id, accion, registro_id, detalle)
        values (new.brote_id, auth.uid(), 'crear', new.id, to_jsonb(new));
        return new;
    elsif (tg_op = 'UPDATE') then
        insert into historial_cambios (brote_id, usuario_id, accion, registro_id, detalle)
        values (new.brote_id, auth.uid(), 'actualizar', new.id, jsonb_build_object('antes', to_jsonb(old), 'despues', to_jsonb(new)));
        return new;
    elsif (tg_op = 'DELETE') then
        -- Si el brote ya no existe, es que se está borrando el brote
        -- completo (cascada) y este registro se va con él: no auditar,
        -- porque violaría la llave foránea de historial_cambios.
        if exists (select 1 from brotes where id = old.brote_id) then
            insert into historial_cambios (brote_id, usuario_id, accion, registro_id, detalle)
            values (old.brote_id, auth.uid(), 'eliminar', old.id, to_jsonb(old));
        end if;
        return old;
    end if;
    return null;
end;
$$;
drop trigger if exists trg_historial_registros on registros_diarios;
create trigger trg_historial_registros after insert or update or delete on registros_diarios
    for each row execute function registrar_historial_registro();

-- =========================================================================
-- MIGRACIÓN: Dashboard público + eliminar usuarios (admin)
-- =========================================================================
alter table brotes add column if not exists token_publico uuid;

create or replace function generar_token_publico(p_brote_id bigint) returns uuid
language plpgsql security definer as $$
declare v_token uuid;
begin
    if not exists (select 1 from brotes b where b.id = p_brote_id and b.usuario_id = auth.uid()) then
        raise exception 'Solo el dueño puede generar el enlace público';
    end if;
    v_token := gen_random_uuid();
    update brotes set token_publico = v_token where id = p_brote_id;
    return v_token;
end;
$$;
grant execute on function generar_token_publico(bigint) to authenticated;

create or replace function revocar_token_publico(p_brote_id bigint) returns void
language plpgsql security definer as $$
begin
    if not exists (select 1 from brotes b where b.id = p_brote_id and b.usuario_id = auth.uid()) then
        raise exception 'Solo el dueño puede revocar el enlace público';
    end if;
    update brotes set token_publico = null where id = p_brote_id;
end;
$$;
grant execute on function revocar_token_publico(bigint) to authenticated;

create or replace function obtener_brote_publico(p_token uuid) returns json
language plpgsql security definer set search_path = public as $$
declare
    v_brote_id bigint; v_nombre text; v_descripcion text; v_registros json;
begin
    select b.id, b.nombre, b.descripcion into v_brote_id, v_nombre, v_descripcion
    from brotes b where b.token_publico = p_token;
    if v_brote_id is null then
        raise exception 'Enlace no válido o revocado';
    end if;
    select json_agg(row_to_json(t)) into v_registros from (
        select r.fecha, r.casos_nuevos, r.fallecidos, r.recuperados,
               v.nombre as via_nombre, u.ciudad, u.pais
        from registros_diarios r
        left join vias_contagio v on v.id = r.via_contagio_id
        left join ubicaciones u on u.id = r.ubicacion_id
        where r.brote_id = v_brote_id order by r.fecha
    ) t;
    return json_build_object('nombre', v_nombre, 'descripcion', v_descripcion, 'registros', coalesce(v_registros, '[]'::json));
end;
$$;
grant execute on function obtener_brote_publico(uuid) to anon, authenticated;

create or replace function admin_eliminar_usuario(p_usuario_id uuid) returns void
language plpgsql security definer set search_path = public, auth as $$
begin
    if not exists (select 1 from perfiles p where p.usuario_id = auth.uid() and p.rol = 'admin') then
        raise exception 'No autorizado: se requiere rol admin';
    end if;
    if p_usuario_id = auth.uid() then
        raise exception 'No puedes eliminar tu propia cuenta desde aquí';
    end if;
    delete from auth.users where id = p_usuario_id;
end;
$$;
grant execute on function admin_eliminar_usuario(uuid) to authenticated;

drop function if exists admin_listar_usuarios();
create or replace function admin_listar_usuarios()
returns table(usuario_id uuid, email text, creado_en timestamptz, confirmado boolean)
language plpgsql security definer set search_path = public, auth as $$
begin
    if not exists (select 1 from perfiles p where p.usuario_id = auth.uid() and p.rol = 'admin') then
        raise exception 'No autorizado: se requiere rol admin';
    end if;
    return query
    select u.id, u.email::text, u.created_at, (u.email_confirmed_at is not null)
    from auth.users u order by u.created_at;
end;
$$;
grant execute on function admin_listar_usuarios() to authenticated;


-- =========================================================================
-- MIGRACIÓN: Configuración global gestionada por admin (ej. ANTHROPIC_API_KEY)
-- =========================================================================
create table if not exists configuracion_global (
    clave          text primary key,
    valor          text,
    actualizado_por uuid references auth.users(id),
    actualizado_en timestamptz default now()
);
alter table configuracion_global enable row level security;
create policy "configuracion_lectura_autenticados" on configuracion_global for select
    using (auth.role() = 'authenticated');

create or replace function guardar_configuracion_admin(p_clave text, p_valor text) returns void
language plpgsql security definer set search_path = public as $$
begin
    if not exists (select 1 from perfiles where usuario_id = auth.uid() and rol = 'admin') then
        raise exception 'No autorizado: se requiere rol admin';
    end if;
    insert into configuracion_global (clave, valor, actualizado_por, actualizado_en)
    values (p_clave, p_valor, auth.uid(), now())
    on conflict (clave) do update set valor = excluded.valor, actualizado_por = excluded.actualizado_por, actualizado_en = now();
end;
$$;
grant execute on function guardar_configuracion_admin(text, text) to authenticated;

-- =========================================================================
-- MIGRACIÓN: Tipo de vía de contagio (respiratoria, zoonótica, etc.)
-- =========================================================================
alter table vias_contagio add column if not exists tipo text
    check (tipo in ('respiratoria', 'contacto_directo', 'zoonotica', 'vectorial', 'hidrica_alimentaria', 'sexual', 'otra'));
