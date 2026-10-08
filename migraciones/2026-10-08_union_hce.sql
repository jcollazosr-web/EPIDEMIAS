-- =========================================================================
-- Unión HCE ↔ EpiScan (2026-10-08). Pegar completo en Supabase → SQL Editor → Run.
-- Se puede ejecutar varias veces sin problema.
-- =========================================================================

-- 1. Seguridad de perfiles: cada usuario solo LEE y ACTUALIZA su fila (no puede borrarla ni recrearse como admin).
drop policy if exists perfil_solo_propio on perfiles;
drop policy if exists perfil_lectura_propia on perfiles;
drop policy if exists perfil_actualizacion_propia on perfiles;
create policy perfil_lectura_propia on perfiles for select to authenticated using (auth.uid() = usuario_id);
create policy perfil_actualizacion_propia on perfiles for update to authenticated
    using (auth.uid() = usuario_id) with check (auth.uid() = usuario_id);

-- 2. Rol y plan: solo los cambia el servidor o un administrador.
create or replace function evitar_autoasignacion_de_rol() returns trigger
language plpgsql security definer set search_path = public as $$
declare
    es_admin boolean := auth.role() = 'service_role'
        or exists (select 1 from perfiles where usuario_id = auth.uid() and rol = 'admin');
begin
    if new.rol is distinct from old.rol and auth.role() <> 'service_role' then
        new.rol := old.rol;
    end if;
    if not es_admin then
        new.plan := old.plan;
        new.plan_actualizado_en := old.plan_actualizado_en;
    end if;
    return new;
end;
$$;

-- 3. Claves de IA: solo administradores y usuarios con plan Pro.
drop policy if exists configuracion_lectura_restringida on configuracion_global;
create policy configuracion_lectura_restringida on configuracion_global for select to authenticated using (
    clave = 'PROVEEDOR_IA_ACTIVO'
    or (clave = any (array['ANTHROPIC_API_KEY','OPENAI_API_KEY','GOOGLE_API_KEY','DEEPSEEK_API_KEY','GROQ_API_KEY'])
        and exists (select 1 from perfiles p where p.usuario_id = auth.uid() and p.plan = 'pro'))
    or exists (select 1 from perfiles p where p.usuario_id = auth.uid() and p.rol = 'admin'));

-- 4. Puente HCE -> EpiScan: funciones que solo usa la función sso-hce (service_role).
create or replace function public.sso_id_por_correo(p_email text) returns uuid
language sql security definer set search_path = public, auth as $$
  select id from auth.users where lower(email) = lower(p_email) limit 1;
$$;

create or replace function public.sso_cerrar_sesiones(p_uid uuid) returns integer
language plpgsql security definer set search_path = public, auth as $$
declare n integer;
begin
  delete from auth.refresh_tokens where user_id = p_uid::text;
  delete from auth.sessions where user_id = p_uid;
  get diagnostics n = row_count;
  return n;
end;
$$;

-- Reemplaza los conteos diarios de los brotes «HCE · …» de la cuenta en el rango de fechas.
-- p_filas: [{brote, via, via_tipo, departamento, municipio, fecha, casos}]
create or replace function public.sso_sincronizar_hce(p_uid uuid, p_desde date, p_hasta date, p_brotes text[],
                                                      p_filas jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  f jsonb; v_brote bigint; v_via bigint; v_ubi bigint; n integer := 0; v_nombre text;
begin
  foreach v_nombre in array p_brotes loop
    if v_nombre not like 'HCE · %' then raise exception 'Nombre de brote no permitido'; end if;
    select id into v_brote from brotes where usuario_id = p_uid and nombre = v_nombre order by id limit 1;
    if v_brote is not null then
      delete from registros_diarios where usuario_id = p_uid and brote_id = v_brote and fecha between p_desde and p_hasta;
    end if;
  end loop;
  for f in select * from jsonb_array_elements(coalesce(p_filas, '[]'::jsonb)) loop
    v_nombre := f->>'brote';
    if not (v_nombre = any (p_brotes)) then continue; end if;
    select id into v_brote from brotes where usuario_id = p_uid and nombre = v_nombre order by id limit 1;
    if v_brote is null then
      insert into brotes (usuario_id, nombre, descripcion) values (p_uid, v_nombre,
        'Generado automáticamente desde la historia clínica: conteos diarios de consultas, sin datos personales.')
      returning id into v_brote;
    end if;
    select id into v_via from vias_contagio where usuario_id = p_uid and nombre = f->>'via';
    if v_via is null then
      insert into vias_contagio (usuario_id, nombre, tipo) values (p_uid, f->>'via', f->>'via_tipo') returning id into v_via;
    end if;
    select id into v_ubi from ubicaciones where usuario_id = p_uid and pais = 'Colombia'
      and departamento is not distinct from nullif(f->>'departamento', '')
      and ciudad is not distinct from nullif(f->>'municipio', '') and barrio is null order by id limit 1;
    if v_ubi is null then
      insert into ubicaciones (usuario_id, pais, departamento, ciudad)
      values (p_uid, 'Colombia', nullif(f->>'departamento', ''), nullif(f->>'municipio', '')) returning id into v_ubi;
    end if;
    insert into registros_diarios (usuario_id, brote_id, fecha, via_contagio_id, ubicacion_id, casos_nuevos, fallecidos, recuperados)
    values (p_uid, v_brote, (f->>'fecha')::date, v_via, v_ubi, greatest((f->>'casos')::int, 0), 0, 0)
    on conflict (usuario_id, fecha, via_contagio_id, ubicacion_id, brote_id)
      do update set casos_nuevos = registros_diarios.casos_nuevos + excluded.casos_nuevos;
    n := n + 1;
  end loop;
  return jsonb_build_object('filas', n);
end;
$$;

-- Casos diarios de los últimos p_dias de todos los brotes de la cuenta (para los avisos de la HCE).
create or replace function public.sso_resumen_hce(p_uid uuid, p_dias integer) returns jsonb
language sql security definer set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object('brote', b.nombre, 'id', b.id, 'serie', s.serie) order by b.nombre), '[]'::jsonb)
  from brotes b
  cross join lateral (
    select coalesce(jsonb_object_agg(r.fecha, r.casos), '{}'::jsonb) as serie
    from (select fecha, sum(casos_nuevos) casos from registros_diarios
          where brote_id = b.id and usuario_id = p_uid and fecha > current_date - p_dias group by fecha) r
  ) s
  where b.usuario_id = p_uid;
$$;

revoke all on function public.sso_id_por_correo(text), public.sso_cerrar_sesiones(uuid),
  public.sso_sincronizar_hce(uuid, date, date, text[], jsonb), public.sso_resumen_hce(uuid, integer)
  from public, anon, authenticated;
grant execute on function public.sso_id_por_correo(text), public.sso_cerrar_sesiones(uuid),
  public.sso_sincronizar_hce(uuid, date, date, text[], jsonb), public.sso_resumen_hce(uuid, integer) to service_role;
