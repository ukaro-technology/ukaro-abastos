# Spec: Horarios de Empleados y Días Libres

**Proyecto:** ukaro-abastos
**Fecha:** 2026-09-05
**Autor:** Claude Code (supervisado por Simón)
**Estado:** borrador — pendiente de decisiones abiertas (sección 7) y aprobación de Simón

## 1. Outcome (Resultado esperado)

Leida puede registrar el horario semanal recurrente de cada empleado (a qué hora entra y a qué
hora sale cada día de la semana) y marcar días libres/vacaciones/permisos puntuales. Cada
empleado puede consultar su propio horario y sus días libres registrados. Es un **calendario de
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
  templates Tailwind con Alpine para interactividad, sin JS inline.

**Consecuencia para el diseño:** esto es una feature completamente nueva, sin nada que migrar ni
ningún comportamiento existente que romper — el único riesgo real de diseño es la app nueva
tocando `accounts.User` vía `ForeignKey`, que ya es un patrón usado en todo el proyecto
(`Sale.user`, `InventoryAdjustment.adjusted_by`, `DailyClose.closed_by`, etc.).

## 3. Scope

### Incluido

- **Horario semanal recurrente por empleado**: para cada uno de los 7 días de la semana, si el
  empleado trabaja ese día y, si trabaja, hora de entrada y hora de salida (`TimeField` nativo de
  Django — no texto ni decimales, para no repetir el bug de coma decimal con `LANGUAGE_CODE=es-ve`
  ya visto dos veces en este proyecto con precios y con la calculadora).
- **Excepciones puntuales** (días libres, vacaciones, permisos, enfermedad): un empleado, un rango
  de fechas (o una sola fecha), un motivo. Mientras dura la excepción, ese empleado se considera
  "no trabaja" esos días completos — sin importar lo que diga su horario recurrente.
- **Vista de administrador** (`admin_required`, como el resto del sistema):
  - Editar el horario semanal de cualquier empleado.
  - Listar, crear y eliminar excepciones (días libres) de cualquier empleado.
  - Vista consolidada: "quién trabaja hoy / esta semana" y "próximos días libres" de todos los
    empleados, para que Leida planifique de un vistazo.
- **Vista de empleado** (autenticado, filtrado a sí mismo): ver su propio horario semanal y sus
  próximas excepciones. Sin edición.
- Historial de cambios vía `django-simple-history` (ya usado en `Product`), para que quede
  registro de quién cambió qué horario y cuándo — gratis, mismo patrón ya establecido.

### Excluido (explícitamente, no "para después" silencioso)

- **Fichaje real** (marcar entrada/salida en el sistema) y cálculo de horas trabajadas —
  decisión explícita: es un calendario de referencia, no un reloj de asistencia.
- **Restricción de acceso al sistema en día libre** — un empleado puede loguearse y hacer ventas
  aunque el sistema diga que ese día no le toca (cubre casos reales: cubrir una emergencia,
  ayudar un rato, etc.). El horario es información, no un candado.
- **Turnos rotativos o múltiples turnos por día** para un mismo empleado (ej. entra, sale a
  almorzar, vuelve) — un solo rango entrada/salida por día es suficiente para el caso real de
  Leida (turno mañana y turno tarde-noche, cada uno con su propio horario, sin partirse en dos).
- **Solicitud/aprobación de días libres por parte del empleado** — Leida es quien registra
  directamente las excepciones; el empleado no pide nada dentro del sistema (puede pedírselo
  a Leida por fuera, como hace hoy).
- **Notificaciones o recordatorios automáticos** (ej. "mañana Juan tiene el día libre") — se puede
  agregar después sin romper nada si Leida lo pide tras usar la feature.
- **Cupos o "banco de vacaciones"** (ej. "12 días de vacaciones al año") — es solo un registro
  libre de excepciones, sin contabilizar límites. Si Leida necesita eso después, es una spec
  aparte.
- **Integración con nómina o pagos** — fuera de alcance total de este sistema hoy.

## 4. Constraints

- Stack: Django + HTMX + Alpine.js + Tailwind (según `CLAUDE.md` del proyecto).
- Single-tenant (este proyecto no tiene multi-tenant, no aplica `.for_tenant()`).
- `USE_TZ = False` — los campos de hora (`TimeField`) no llevan timezone, consistente con el resto
  del sistema.
- `LANGUAGE_CODE = 'es-ve'` — cualquier campo de hora u horario mostrado en un template que se lea
  desde JS (Alpine) debe usar `|unlocalize` si se inyecta en una expresión JS, para no repetir el
  bug de coma decimal ya encontrado dos veces este proyecto (calculadora del navbar, conversor de
  precios). Los `TimeField` no tienen decimales, pero si se muestra alguna duración calculada
  (ej. horas de turno) sí aplicaría.
- Solo administradores pueden crear/editar horarios y excepciones (`admin_required`, mismo patrón
  que el resto del sistema) — el empleado solo tiene acceso de lectura a lo suyo.
- Tests obligatorios antes de merge (suite completa debe seguir en las mismas ~9 failures + 6
  errors preexistentes, sin regresiones nuevas — mismo criterio de verificación que la spec
  anterior, precios-estables-bs).

## 5. Decisions Already Made

Decididas por Simón al inicio de esta sesión:

1. **Alcance**: calendario de horario recurrente + excepciones puntuales. **No** es un sistema de
   fichaje ni calcula horas trabajadas.
2. **Sin restricción de acceso**: el horario es informativo. No bloquea login ni ventas en un día
   marcado como libre.
3. **Turnos CON horario** (hora de entrada y salida por día), no solo "trabaja/no trabaja" — hay
   dos empleados reales con turnos que se superponen parcialmente (el de la mañana se va minutos u
   horas después de que llega el de la tarde-noche), así que hace falta el horario exacto para que
   el modelo tenga sentido.
4. **Solo Leida (admin) edita** horarios y excepciones. El empleado solo ve el suyo, de solo
   lectura.

## 6. Tasks (implementación — a ejecutar solo después de aprobación)

1. [ ] Definir si es una app nueva (`schedules`) o vive dentro de `accounts` (ver decisión 7.1).
2. [ ] Modelo `WeeklySchedule` (empleado, día de semana 0-6, trabaja ese día, hora entrada, hora
   salida) + `HistoricalRecords()`.
3. [ ] Modelo `ScheduleException` (empleado, fecha inicio, fecha fin, tipo de excepción, motivo
   libre opcional) + `HistoricalRecords()`.
4. [ ] Migraciones.
5. [ ] `WeeklyScheduleForm` (formset de 7 días por empleado) y `ScheduleExceptionForm`.
6. [ ] Vista admin: editar horario semanal de un empleado (`admin_required`).
7. [ ] Vista admin: listar/crear/eliminar excepciones de un empleado (`admin_required`).
8. [ ] Vista admin: panel consolidado "quién trabaja hoy/esta semana" + "próximos días libres" de
   todos los empleados.
9. [ ] Vista de empleado: ver su propio horario y sus excepciones (solo lectura, filtrado a
   `request.user`).
10. [ ] Templates (Tailwind, Alpine sin JS inline, siguiendo convenciones del resto del sistema).
11. [ ] Entrada de menú en la navegación (`base.html`) visible según rol.
12. [ ] Tests: modelos, formularios, vistas (permisos admin vs empleado), casos de excepción que
    se superpone con el horario recurrente.
13. [ ] Actualizar `docs/PENDIENTES.md` al cerrar.

## 7. Preguntas abiertas (decidir antes de implementar)

1. **App nueva vs. extender `accounts`**: ¿creamos una app nueva (`schedules` o `horarios`, más
   alineado con la convención del proyecto de "un módulo por dominio de negocio" del `CLAUDE.md`),
   o lo metemos dentro de `accounts` ya que gira en torno al `User`? **Recomendado: app nueva**,
   consistente con cómo están organizados `inventory`, `sales`, `customers`, etc.
2. **Granularidad de las excepciones**: ¿alcanza con "día completo libre", o hace falta contemplar
   medio día / "sale más temprano tal día en particular" sin ser una excepción completa?
   **Recomendado: día completo únicamente** en esta primera versión — más simple, cubre el caso
   real de vacaciones/permisos/enfermedad.
3. **Tipos de excepción**: ¿categorías fijas (ej. `vacaciones` / `permiso` / `enfermedad` / `otro`)
   con un choice field, o simplemente fecha(s) + un campo de texto libre para el motivo?
   **Recomendado: categorías fijas + texto libre opcional** — no cuesta nada implementarlo y sirve
   si más adelante Leida quiere un reporte de "cuántos días de enfermedad tomó cada quien este
   año", sin tener que parsear texto libre después.
4. **Vista del panel consolidado**: ¿una tabla simple (recomendado, consistente con el resto del
   sistema — sin JS de calendario) o un calendario visual tipo grid mensual (bastante más trabajo
   de frontend, requeriría una librería o Alpine bastante elaborado)? **Recomendado: tabla simple.**
5. **Cambios de horario frecuentes**: ¿los turnos de los dos empleados son prácticamente fijos casi
   todo el tiempo, o cambian seguido (ej. rotan semana por medio)? Esto decide si vale la pena una
   función de "duplicar el horario de la semana pasada" o si alcanza con un formulario simple de
   "editar mi horario recurrente" que rara vez se toca. **Asumido por ahora: cambian poco**, un
   formulario simple alcanza — pero vale confirmarlo porque cambia el esfuerzo de UI.

## 8. Verification (cómo verificar antes de dar por cerrada la spec)

- [ ] Tests pasan (`python manage.py test`), sin regresiones sobre el baseline conocido.
- [ ] Prueba manual: Leida configura el horario semanal de ambos empleados reales (turno mañana y
  turno tarde-noche, con la superposición real entre ambos) y lo ve reflejado correctamente.
- [ ] Prueba manual: Leida marca un día libre puntual para un empleado (ej. una semana de
  vacaciones) y confirma que aparece en el panel consolidado y en la vista propia del empleado.
- [ ] Prueba manual: el empleado con día libre puede seguir logueándose y operando el sistema sin
  ningún bloqueo (confirma que la decisión de "sin restricción" quedó bien implementada).
- [ ] Review de Simón (y de Leida, si hace falta validar el flujo desde el punto de vista de uso
  diario).
