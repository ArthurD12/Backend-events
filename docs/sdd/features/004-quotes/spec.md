# Spec: Cotizaciones (elaborar, actualizar y controlar su estado)

- **ID**: 004-quotes
- **Estado**: aprobado (César Suclupe, 22/11/2026)
- **Módulos afectados**: `commercial` (submódulo `quotes`), `catalog` (solo lectura, vía `public_api`), `identity` (permiso nuevo)
- **Historias**: HU07 (#8), HU08 (#9)

## 1. Problema y objetivo
Hoy las propuestas económicas de Darze se arman a mano: se repiten precios, los totales se calculan con calculadora y no queda claro qué se le ofreció a cada cliente ni en qué quedó. El objetivo es que el encargado de eventos arme la cotización en el sistema, con los servicios del catálogo, los totales automáticos y un código único, y que pueda seguir su estado hasta que el cliente la acepte o la rechace.

## 2. Usuarios / actores
- **Encargado de eventos** y **administrador**: elaboran, modifican y siguen las cotizaciones.
- **Encargado de compras y almacén**: no usa cotizaciones (DOMAIN.md §9).

## 3. Historias de usuario
- **HU07**: Como encargado de eventos, quiero elaborar una cotización con los datos del cliente y los servicios solicitados, para presentar una propuesta económica.
- **HU08**: Como encargado de eventos, quiero actualizar y controlar el estado de las cotizaciones, para realizar su seguimiento comercial.

## 4. Criterios de aceptación
### HU07: elaborar
- **CA-07.1**: Solo se puede elegir un cliente **activo**.
- **CA-07.2**: Se registran el tipo de evento, la fecha, el horario (inicio y fin), el lugar, la cantidad de invitados y la vigencia.
- **CA-07.3**: Se agregan servicios del catálogo (menús, bebidas, mobiliario…) con cantidad y precio, y **conceptos adicionales** libres (descripción y monto). Solo se agregan servicios **activos**.
- **CA-07.4**: El sistema genera un **código único** `COT-AAAA-NNNN`.
- **CA-07.5**: El subtotal de cada línea (cantidad × precio) y el total se calculan solos, en la pantalla y en el servidor.
- **CA-07.6**: La cotización se guarda en estado **borrador**.

### HU08: actualizar y controlar el estado
- **CA-08.1**: Una cotización en **borrador** se puede modificar (datos del evento, líneas, cantidades y precios).
- **CA-08.2**: El estado cambia a **enviada**, **aceptada** o **rechazada** según las transiciones de la regla R-COT-3.
- **CA-08.3**: Una cotización que supera su vigencia sin ser aceptada se muestra como **vencida**.
- **CA-08.4**: Las cotizaciones aceptadas, rechazadas o vencidas no se modifican, ni desde la API ni desde la base de datos.
- **CA-08.5**: Se buscan por código, cliente, fecha del evento y estado.

## 5. Reglas de negocio
Las reglas 1, 2 y 6 a 14 de `DOMAIN.md` §4 aplican tal como están. Se resumen las que más pesan:
- Los precios se **congelan** en la cotización: cambiar el catálogo no la altera. Se guarda el precio del catálogo y el precio acordado (regla 10).
- Vigencia de **15 días** por defecto, editable (regla 7). Precios en soles, **sin IGV** aparte (regla 9).
- En los servicios **por persona**, la cantidad propuesta es el número de invitados y se puede editar (regla 11).
- La cotización **no reserva** la fecha (regla 6). Una rechazada o vencida no se reabre: se hace una nueva (regla 14).

Reglas nuevas, decididas por el equipo el 22/11/2026 *(provisionales)*:
- **R-COT-1**: el horario puede cruzar la medianoche. Si la hora de fin es menor que la de inicio, el evento termina al día siguiente (20:00 → 03:00). Inicio y fin no pueden ser iguales.
- **R-COT-2**: para cambiar una cotización **enviada**, se devuelve a **borrador**, se edita y se vuelve a enviar.
- **R-COT-3**: transiciones permitidas:
  - borrador → enviada, aceptada o rechazada;
  - enviada → aceptada, rechazada o borrador;
  - aceptada y rechazada son finales; una vencida no cambia de estado.
- **R-COT-4**: la fecha del evento es **hoy o una fecha futura** (hora de Lima).
- **R-COT-5**: una cotización tiene **al menos una línea**, y la cantidad de invitados es mayor que cero.

## 6. Fuera de alcance
- PDF de la cotización (HU09), contrato y adelanto (HU41–HU42), conversión en evento (HU10).
- Cotización por alumno para promociones (`DOMAIN.md` §10, pregunta 2): se tratará como una historia aparte.
- Descuentos como campo separado (regla 10: se ajusta el precio de la línea).

## 7. Requisitos no funcionales
- **Auditoría**: se guarda qué usuario creó la cotización y cuándo (RN03).
- **Concurrencia**: dos cotizaciones creadas al mismo tiempo nunca reciben el mismo código.
- **Mantenimiento mínimo**: el estado "vencida" se calcula al consultar, sin tareas programadas ni servicios nuevos.

## 8. Preguntas abiertas
- [x] ¿El horario cruza medianoche? → Sí (César, 22/11/2026).
- [x] ¿Cómo se cambia una enviada? → Vuelve a borrador (César, 22/11/2026).
- [x] ¿Borrador directo a aceptada o rechazada? → Sí (César, 22/11/2026).
- [x] ¿Fecha del evento en el pasado? → No (César, 22/11/2026).
- [ ] Informar al Product Owner las reglas R-COT-1 a R-COT-5.
