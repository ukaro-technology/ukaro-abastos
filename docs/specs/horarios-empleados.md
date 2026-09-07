# Spec: Horarios de Empleados y Días Libres

**Proyecto:** ukaro-abastos
**Fecha:** 2026-09-05 (corregida: 2026-09-07)
**Autor:** Claude Code (supervisado por Simón)
**Estado:** borrador — pendiente de aprobación final de Simón

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

## 6. Tasks (implementación — a ejecutar solo después de aprobación)

1. [ ] Crear app nueva `schedules`, registrarla en `INSTALLED_APPS`.
2. [ ] Modelo `Shift` (Turno): `name`, `start_time`, `end_time` + `HistoricalRecords()`. Data
   migration que crea los 2 turnos iniciales (Mañana 7:00-15:00, Tarde 13:00-21:00).
3. [ ] Modelo `ShiftAssignment` (AsignacionDeTurno): `date`, `shift` (FK), `employee` (FK a
   `accounts.User`), `unique_together` en (`date`, `shift`) — un solo empleado por turno por día.
   + `HistoricalRecords()`.
4. [ ] Modelo `ScheduleException` (ExcepcionDeHorario): `employee`, `date_start`, `date_end`,
   `exception_type` (choices), `reason` (texto libre opcional) + `HistoricalRecords()`.
5. [ ] Validación: no permitir crear/editar una `ShiftAssignment` para un empleado en una fecha
   cubierta por una `ScheduleException` activa de ese mismo empleado.
6. [ ] Migraciones.
7. [ ] Vista admin: planilla semanal editable — tabla de 7 días × 2 turnos, edición inline por
   celda vía HTMX (`admin_required`). Navegación entre semanas (anterior/siguiente).
8. [ ] Vista admin: listar/crear/eliminar excepciones por empleado (`admin_required`).
9. [ ] Vista de empleado: planilla semanal de solo lectura + sus propias excepciones próximas.
10. [ ] Templates (Tailwind, HTMX/Alpine sin JS inline, siguiendo convenciones del resto del
    sistema).
11. [ ] Entrada de menú en la navegación (`base.html`) visible según rol.
12. [ ] Tests: modelos (`unique_together`, validación de excepción vs. asignación), vistas
    (permisos admin vs. empleado), edición inline vía HTMX.
13. [ ] Actualizar `docs/PENDIENTES.md` al cerrar.

## 7. Verification (cómo verificar antes de dar por cerrada la spec)

- [ ] Tests pasan (`python manage.py test`), sin regresiones sobre el baseline conocido.
- [ ] Prueba manual: Leida arma la planilla de una semana real con sus dos empleados rotando entre
  mañana y tarde (incluyendo un día donde cambian respecto al día anterior) y la ve reflejada
  correctamente.
- [ ] Prueba manual: Leida marca un día libre puntual para un empleado (ej. una semana de
  vacaciones) y confirma que no se lo puede asignar a un turno esos días (validación) y que la
  excepción aparece en su vista propia.
- [ ] Prueba manual: el empleado con día libre puede seguir logueándose y operando el sistema sin
  ningún bloqueo (confirma que la decisión de "sin restricción" quedó bien implementada).
- [ ] Review de Simón (y de Leida, si hace falta validar el flujo desde el punto de vista de uso
  diario).
