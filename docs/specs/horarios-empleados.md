# Spec: Horarios de Empleados y Días Libres

**Proyecto:** ukaro-abastos
**Fecha:** 2026-09-05 (corregida: 2026-09-07, implementada: 2026-09-07)
**Autor:** Claude Code (supervisado por Simón)
**Estado:** implementada — pendiente de prueba manual de Simón/Leida (ver sección 7)

## 1. Outcome (Resultado esperado)

Leida puede armar la planilla de turnos de sus dos empleados (quién cubre el turno mañana y quién
el turno tarde en cada día) y marcar días libres/vacaciones/permisos puntuales. Cada empleado
puede consultar la planilla y sus propios días libres. Es un **calendario/planilla de
referencia**, no un sistema de fichaje — no calcula horas trabajadas, no bloquea el acceso al
sistema en un día libre, y no requiere que nadie "marque entrada".

## 2. Cómo funciona el sistema HOY (hallazgo, punto de partida real)

Investigado antes de diseñar: **no existe ningún concepto de horario, turno o asistencia en el
proyecto hoy.**

- `accounts.User` (`accounts/models.py`) solo tiene `is_admin`/`is_employee` como booleanos —
  ningún otro dato del empleado (sin fecha de contratación, teléfono, etc.). Es un
  `AbstractUser` de Django estándar.
- Lo más cercano a "actividad de un empleado en el tiempo" que existe hoy es `performance`
  (`performance/views.py:_get_user_stats`) — un dashboard de ventas por usuario en un rango de
  fechas — y `Sale.user` (quién hizo cada venta). Ninguno de los dos tiene relación con horario o
  asistencia; son solo reportes de ventas.
- `finances.DailyClose` es **uno por día para toda la bodega** (`date` es `unique=True`), no por
  empleado — guarda quién lo cerró (`closed_by`) pero no qué turno trabajó cada quien ese día.
- Todas las vistas administrativas de gestión (usuarios, productos, categorías, ajustes) siguen
  el mismo patrón: `@admin_required` para crear/editar, CBV o FBV según la complejidad del CRUD,
  templates Tailwind con Alpine/HTMX para interactividad, sin JS inline.

**Consecuencia para el diseño:** esto es una feature completamente nueva, sin nada que migrar ni
ningún comportamiento existente que romper — el único punto de integración real es la app nueva
tocando `accounts.User` vía `ForeignKey`, patrón ya usado en todo el proyecto (`Sale.user`,
`InventoryAdjustment.adjusted_by`, `DailyClose.closed_by`, etc.).

## 3. Scope

### Incluido

- **Turnos fijos** (`Turno`): Mañana (7:00am–3:00pm) y Tarde (1:00pm–9:00pm), definidos una vez.
  Editable por admin por si algún día cambian los horarios — no hardcodeado en el código, para no
  necesitar un deploy solo para ajustar una hora.
- **Planilla de asignación de turnos** (`AsignacionDeTurno`): por cada día y cada turno, qué
  empleado lo cubre. **Esto reemplaza la idea original de "horario semanal recurrente"** — Leida
  aclaró que los dos empleados rotan entre mañana y tarde sin un patrón semanal fijo (un día uno
  hace mañana y el otro tarde, al día siguiente puede ser al revés), así que un horario "plantilla
  que se repite cada semana" no representa la realidad. Con la planilla, Leida asigna día a día (o
  semana a semana) quién cubre cada turno — no hay que "mantener sincronizada" ninguna plantilla.
- **Excepciones puntuales** (días libres, vacaciones, permisos, enfermedad) — `ExcepcionDeHorario`:
  un empleado, un rango de fechas (o una sola fecha), un tipo de motivo (categoría fija +
  texto libre opcional). Mientras dura la excepción, ese empleado se considera "no disponible" esos
  días completos. **Validación**: no se puede asignar un empleado a un turno en una fecha donde
  tiene una excepción activa (evita datos contradictorios en la planilla).
- **Vista de administrador** (`admin_required`, como el resto del sistema):
  - Planilla semanal editable (tabla: filas = días, columnas = Mañana/Tarde, celda = selector de
    empleado) — edición inline vía HTMX, sin recargar la página completa por cada cambio.
  - Listar, crear y eliminar excepciones (días libres) de cualquier empleado.
  - La planilla semanal ES la vista consolidada — muestra a los dos empleados en los dos turnos de
    un vistazo, no hace falta una pantalla aparte de "quién trabaja hoy".
- **Vista de empleado** (autenticado, de solo lectura): ver la planilla de la semana y sus propias
  próximas excepciones. Sin edición.
- Historial de cambios vía `django-simple-history` (ya usado en `Product`), para que quede
  registro de quién cambió qué asignación y cuándo — gratis, mismo patrón ya establecido.

### Excluido (explícitamente, no "para después" silencioso)

- **Fichaje real** (marcar entrada/salida en el sistema) y cálculo de horas trabajadas —
  decisión explícita: es un calendario de referencia, no un reloj de asistencia.
- **Restricción de acceso al sistema en día libre** — un empleado puede loguearse y hacer ventas
  aunque el sistema diga que ese día no le toca (cubre casos reales: cubrir una emergencia,
  ayudar un rato, etc.). El horario es información, no un candado.
- **Calendario visual tipo grid mensual** — por ahora es una tabla simple (semanal), consistente
  con el resto del sistema. Decisión explícita de Simón: "por ahora tabla simple, luego el
  calendario" — queda como evolución futura, no de esta spec.
- **Solicitud/aprobación de días libres por parte del empleado** — Leida es quien registra
  directamente las excepciones; el empleado no pide nada dentro del sistema (puede pedírselo
  a Leida por fuera, como hace hoy).
- **Notificaciones o recordatorios automáticos** (ej. "mañana Juan tiene el día libre") — se puede
  agregar después sin romper nada si Leida lo pide tras usar la feature.
- **Cupos o "banco de vacaciones"** (ej. "12 días de vacaciones al año") — es solo un registro
  libre de excepciones, sin contabilizar límites. Si Leida necesita eso después, es una spec
  aparte.
- **Excepciones de medio día** (ej. "sale 2 horas antes puntualmente") — solo día completo en esta
  versión. Decisión explícita de Simón: "día completo por ahora".
- **Integración con nómina o pagos** — fuera de alcance total de este sistema hoy.

## 4. Constraints

- Stack: Django + HTMX + Alpine.js + Tailwind (según `CLAUDE.md` del proyecto). La planilla
  editable es un caso natural para HTMX (edición inline por celda sin recargar la página) — mismo
  patrón que otras partes del sistema ya resuelven así (ver skill `htmx-patterns`).
- Single-tenant (este proyecto no tiene multi-tenant, no aplica `.for_tenant()`).
- `USE_TZ = False` — los campos `TimeField`/`DateField` no llevan timezone, consistente con el
  resto del sistema.
- Solo administradores pueden crear/editar turnos, asignaciones y excepciones (`admin_required`,
  mismo patrón que el resto del sistema) — el empleado solo tiene acceso de lectura.
- Tests obligatorios antes de merge (suite completa debe seguir en las mismas ~9 failures + 6
  errors preexistentes, sin regresiones nuevas — mismo criterio de verificación que la spec
  anterior, precios-estables-bs).

## 5. Decisions Already Made

Decididas por Simón en esta sesión:

1. **Alcance**: planilla de turnos + excepciones puntuales. **No** es un sistema de fichaje ni
   calcula horas trabajadas.
2. **Sin restricción de acceso**: el horario es informativo. No bloquea login ni ventas en un día
   marcado como libre.
3. **Turnos fijos con horario** (Mañana 7:00am-3:00pm, Tarde 1:00pm-9:00pm) — no "trabaja/no
   trabaja" genérico.
4. **Solo Leida (admin) edita** la planilla y las excepciones. El empleado solo ve, de solo
   lectura.
5. **App nueva** (`schedules`) — consistente con la convención del proyecto de "un módulo por
   dominio de negocio", en vez de meterlo dentro de `accounts`.
6. **Excepciones de día completo únicamente** en esta versión — sin granularidad de medio día.
7. **Tipos de excepción con categorías fijas** (`vacaciones` / `permiso` / `enfermedad` / `otro`)
   + campo de texto libre opcional para el detalle — permite reportes futuros sin tener que
   parsear texto libre.
8. **Tabla simple, no calendario visual** — por ahora. El calendario visual queda como evolución
   futura explícita, no de esta spec.
9. **Planilla de asignación día a día, no horario recurrente semanal** — porque los dos empleados
   rotan entre los turnos mañana/tarde sin un patrón fijo semanal (hallazgo real que corrigió el
   diseño original de esta spec, ver sección 2 y 3).

## 6. Tasks (implementación)

1. [x] App nueva `schedules`, registrada en `INSTALLED_APPS` + URL raíz `schedules/`.
2. [x] Modelo `Shift` (Turno): `name`, `start_time`, `end_time` + `HistoricalRecords()`. Data
   migration (`0002_seed_default_shifts`) que crea Mañana (7:00-15:00) y Tarde (13:00-21:00).
3. [x] Modelo `ShiftAssignment`: `date`, `shift` (FK), `employee` (FK a `accounts.User`),
   `unique_together` en (`date`, `shift`) + `HistoricalRecords()`.
4. [x] Modelo `ScheduleException`: `employee`, `date_start`, `date_end`, `exception_type`
   (choices: vacaciones/permiso/enfermedad/otro), `reason` (texto libre opcional),
   `created_by` + `HistoricalRecords()`.
5. [x] Validación en `ShiftAssignment.clean()`: rechaza asignar un turno a un empleado en una
   fecha cubierta por una `ScheduleException` suya. De paso, `ScheduleException` creada sobre un
   rango con asignaciones existentes **no bloquea** — avisa con `messages.warning()` (no estaba
   en la spec original, ver sección 9.1).
6. [x] Migraciones (`0001_initial`, `0002_seed_default_shifts`).
7. [x] Vista admin: planilla semanal editable (`week_view`) — tabla de días × turnos, cada celda
   es un `<select>` con `hx-post`/`hx-trigger="change"` que swappea solo esa celda
   (`hx-swap="outerHTML"`), sin recargar la página. Navegación `?week=YYYY-MM-DD` (anterior/
   siguiente/volver a hoy).
8. [x] Vista admin: `exception_list` (listar, admin ve todas), `exception_create` (form
   completo), `exception_delete` (HTMX `hx-delete`, animación de fila, sin modal — ver sección
   9.2). `shift_list`/`shift_update` para editar el horario de los turnos fijos.
9. [x] Vista de empleado: misma `week_view` en modo solo lectura (texto plano, sin `<select>`) +
   `exception_list` filtrada a `request.user`.
10. [x] Templates Tailwind, HTMX declarativo (sin `on*` inline), siguiendo la convención real del
    proyecto (formularios de página completa, no modal — ver sección 9.2).
11. [x] Entrada "Horarios" en `base.html`, visible para admin y empleado (mismo lugar que
    "Inventario").
12. [x] 32 tests nuevos en `schedules`: modelos, `unique_together`, validación de conflicto,
    permisos por vista, endpoint HTMX de asignación (asignar/reasignar/desasignar/bloqueo por
    excepción), excepciones (crear/listar/eliminar/aviso de conflicto), edición de turnos.
13. [ ] Actualizar `docs/PENDIENTES.md` al cerrar (pendiente, se hace al final de esta sesión).

## 7. Verification

- [x] Tests pasan (`python manage.py test`) — 494 tests totales (+32 nuevos de esta sesión),
  mismas 9 failures + 6 errors preexistentes que en la sesión anterior, cero regresiones nuevas.
- [x] Verificado el endpoint HTMX end-to-end con requests HTTP reales (login real + POST con
  header `X-CSRFToken`, contra el servidor local) — asignar, reasignar, desasignar. **Sin
  verificación visual con navegador real**: la extensión de Chrome no estaba conectada esta
  sesión, así que no se pudo confirmar que el `<select>` dispara `hx-trigger="change"`
  correctamente en un navegador de verdad (el HTML/HTTP están confirmados correctos, pero el
  comportamiento del JS de HTMX en el navegador no se vio con los propios ojos). Pendiente
  para la próxima sesión o para cuando Simón/Leida lo prueben.
- [ ] Prueba manual pendiente (Simón/Leida): armar la planilla de una semana real rotando entre
  mañana y tarde, marcar un día libre y confirmar que se ve reflejado, confirmar que el empleado
  con día libre sigue pudiendo loguearse y vender sin bloqueo.
- [ ] Review de Simón.

## 8. Notas de implementación (hallazgos durante el desarrollo, no cambian el diseño aprobado)

1. **`ScheduleException` creada sobre un rango con turnos ya asignados no bloquea la creación** —
   decisión tomada durante la implementación, no estaba en la spec original. Bloquear habría sido
   más estricto pero más incómodo (Leida a veces va a registrar la excepción DESPUÉS de haber
   armado la planilla). En cambio, se avisa con un mensaje ("X ya tenía turnos asignados en este
   rango: ...") para que Leida sepa que hay que reasignar esos turnos a otra persona.
2. **Se confirmó que HTMX nunca se había usado realmente en el proyecto** — el paquete
   `django-htmx` y el middleware estaban instalados, el script CDN estaba cargado en `base.html`,
   pero cero templates lo usaban. Esta es la primera feature real. Se agregó lo que faltaba para
   que funcione: la regla CSS `.htmx-indicator` (estándar de HTMX, no existía) y `hx-headers` con
   el token CSRF en el `<body>` (sin esto, cualquier `hx-post`/`hx-delete` habría fallado con 403
   por falta de CSRF). También se confirmó que el patrón de modal de la skill `htmx-patterns`
   (`<c-ukaro.overlay.modal>`) **no aplica a este proyecto** — ukaro-abastos no usa `ukaro-ui`
   (Tailwind CDN + crispy-tailwind, sin componentes cotton), así que los formularios de excepción/
   turno se hicieron como páginas completas, igual que `product_create`/`product_update` en
   `inventory`, no como modales.
