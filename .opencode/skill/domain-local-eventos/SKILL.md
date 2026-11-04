---
name: domain-local-eventos
description: Reglas de negocio del local de eventos (salones por horas, paquetes Normal/Pro/Premium, servicios, cobros en ledger, inventario perecible, rentabilidad por evento, roles). Úsala al escribir specs, planes o código que toque reservas, catálogo, ledger o inventario.
---

# Dominio del local de eventos

Fuente completa: `docs/DOMAIN.md`. Resumen operativo:

- **Salones:** uno por piso, no divisibles, alquiler **por horas**, con montaje y limpieza. Sin solapes (restricción en PostgreSQL).
- **Reserva:** eje del sistema. Estados `cotizada → reservada → confirmada → realizada → cerrada` y `cancelada`. Todo lo vendido está ligado a una reserva.
- **Paquetes** Normal/Pro/Premium con composición fija (personas, mozos, tipos de comida, anfitriona, bartender…). **Eventos personalizados** por ítems (horas, bartenders y horas, comida, mozos, anfitrionas, torta, camarógrafos…).
- **Servicios** con unidad de cobro: por hora, persona, unidad o evento.
- **Precios congelados** en la reserva.
- **Ledger** append-only en `PEN` (céntimos): adelantos, cuotas, saldo, egresos, reversiones. Sin pasarela. Cerveza ocasional = ingreso manual `venta_bebida`.
- **Inventario** solo de perecibles y consumibles del evento (barra, cocina, evento). **Sin equipos ni mobiliario.** Lotes con vencimiento, FEFO, estimado vs real, mermas.
- **Rentabilidad por evento** = ingresos − insumos consumidos − servicios − otros egresos.
- **Roles:** administrador (todo), vendedor (clientes, cotizar/reservar, registrar cobros), almacén (inventario). Permisos por capacidad.

## Cuando falte una regla
Está en "por validar" en DOMAIN.md → **pregunta al humano**. No inventes políticas de cancelación, descuentos, costeo ni costos de personal.
