-- Infraestructura de registro sin correo, aplicada en el proyecto Supabase de Mini Yolotzin.
-- Solo el backend (service_role) puede incrementar el contador de registros.
create table if not exists public.mini_registro_limites (
  clave text not null check (length(clave) between 32 and 128),
  ventana timestamptz not null,
  intentos integer not null default 0 check (intentos >= 0),
  primary key (clave, ventana)
);
alter table public.mini_registro_limites enable row level security;
revoke all on public.mini_registro_limites from anon, authenticated, public;
grant select, insert, update on public.mini_registro_limites to service_role;

create or replace function public.mini_consumir_cupo_registro(p_clave text)
returns boolean language plpgsql security invoker set search_path = ''
as $lim$
declare v_count integer;
begin
  if p_clave is null or length(p_clave) < 32 or length(p_clave) > 128 then return false; end if;
  insert into public.mini_registro_limites as lim(clave, ventana, intentos)
  values (p_clave, date_bin('10 minutes', now(), '2020-01-01 00:00:00+00'::timestamptz), 1)
  on conflict(clave, ventana)
  do update set intentos=lim.intentos + 1 where lim.intentos < 80
  returning intentos into v_count;
  return v_count is not null and v_count <= 80;
end;
$lim$;
revoke all on function public.mini_consumir_cupo_registro(text) from public, anon, authenticated;
grant execute on function public.mini_consumir_cupo_registro(text) to service_role;