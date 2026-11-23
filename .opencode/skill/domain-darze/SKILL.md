---
name: domain-darze
description: Reglas de negocio de Darze (catering): cotización → contrato → evento, personal y asignaciones sin cruces, pagos append-only, almacén, requerimientos y compras, agente de IA de solo consulta y roles. Úsala al escribir specs, planes o código de cualquier módulo de negocio.
---

# Dominio de Darze

Fuente completa: `docs/DOMAIN.md` (reglas RN01–RN33 del documento validado por Darze). Resumen operativo:

- **Flujo:** cliente → cotización → contrato → evento → personal, materiales y compras → pagos. Darze atiende en el lugar del cliente: **no hay salones propios**.
- **Cotización:** `borrador → enviada → aceptada | rechazada | vencida`. Solo se edita en borrador; vence al terminar su vigencia. Precios **congelados** en la cotización.
- **Contrato:** se genera solo desde una cotización aceptada sin contrato previo. `pendiente de firma → firmado | anulado`. Adelanto 50 % por defecto; saldo hasta 7 días antes del evento. Firmado = no editable; anular exige motivo.
- **Evento:** nace de un contrato firmado con adelanto pagado, una sola vez. `programado → confirmado → en ejecución → finalizado` y `cancelado`. Cancelar no borra pagos ni movimientos.
- **Personal:** solo trabajadores activos y disponibles; **un trabajador no puede tener dos asignaciones con horarios superpuestos** (restricción en PostgreSQL).
- **Dinero** en `PEN` (céntimos), append-only: pago > 0 y ≤ saldo; saldo = contratado − pagos + anulaciones. El adelanto se registra desde el contrato como primer pago.
- **Almacén:** movimientos append-only (entrada, salida, devolución, merma con motivo); salida ≤ stock; alertas de stock mínimo y vencimiento. Requerimientos según menú, servicios e invitados. La compra suma stock solo al estar **recibida**.
- **Agente de IA:** solo consulta, solo datos permitidos al rol, mediante funciones del backend (nunca SQL directo); pide aclaración si es ambiguo; no inventa; registra cada consulta.
- **Roles:** administrador (todo), encargado de eventos (clientes, cotizaciones, contratos, eventos, personal), encargado de compras y almacén (productos, almacén, compras). Permisos por capacidad. Nada con operaciones relacionadas se elimina: se desactiva.

## Cuando falte una regla
Está en "por validar" en DOMAIN.md → **pregunta al humano**. No inventes políticas de cancelación, descuentos, costeo ni pagos.
