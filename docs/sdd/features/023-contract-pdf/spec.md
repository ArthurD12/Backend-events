# Spec: Contrato en PDF

- **ID**: 023-contract-pdf
- **Estado**: aprobado por el Product Owner (César Suclupe, 26/11/2026)
- **Módulos afectados**: `commercial` (submódulo `contracts`)
- **Historia**: HU43 (#44), RF104. Prioridad Should. Sale del "fuera de alcance" de `005-contracts`.

## 1. Problema y objetivo
El contrato ya se genera y se firma en el sistema, pero al cliente hay que entregarle un documento. Hoy se redactaría a mano. El objetivo es descargar un PDF generado desde lo registrado, con las condiciones y los espacios de firma, listo para imprimir y entregar.

## 2. Actores
- **Encargado de eventos** y **administrador** (permiso `contracts:manage`, el mismo de los demás endpoints de contratos).

## 3. Historia
- **HU43**: Como encargado de eventos, quiero descargar el contrato en PDF, para entregarlo al cliente.

## 4. Criterios de aceptación
- **CA-43.1**: El PDF muestra los datos de Darze (los de `.env`, como en la cotización) y los del cliente: nombre, documento, teléfono y correo.
- **CA-43.2**: Muestra el evento (tipo, fecha, horario, lugar e invitados), los servicios con cantidad, precio y subtotal, y los montos: total, adelanto y saldo con su fecha límite.
- **CA-43.3**: Muestra las condiciones y la política de cancelación (RF104), y los espacios de firma del cliente y de Darze.
- **CA-43.4**: Coincide con el contrato registrado: los montos, fechas y servicios salen de lo guardado (contrato y su cotización congelada), no del catálogo actual. Si está firmado, indica la fecha de firma y el firmante.
- **CA-43.5**: Se descarga como `CON-AAAA-NNNN.pdf`. Generarlo no cambia el contrato.
- **CA-43.6**: Un contrato anulado responde `contract.pdf_not_available` (409); en la pantalla el botón aparece deshabilitado con su motivo.

## 5. Reglas
- **R-PDF-2** *(decidido por el equipo el 26/11/2026, provisional)*: se descarga un contrato **pendiente de firma** (para firmarlo en papel) o **firmado** (copia para el cliente). Uno **anulado** no: nunca se entrega un contrato sin valor, y se evita una variante con marca "ANULADO". Es el mismo criterio de R-PDF-1.
- **R-PDF-3** *(provisional)*: lo puede descargar quien gestiona contratos (`contracts:manage`).
- **R-PDF-4** *(provisional)*: el texto de las **condiciones** es fijo y sale del código. No inventa reglas: reproduce lo decidido (R-CON-3: anulación con motivo y sin penalidades ni devoluciones automáticas; R-EVT-4: para cambiar algo de un contrato firmado se anula y se hace otra cotización; precios en soles sin IGV aparte; saldo hasta la fecha límite). Darze debe confirmar o reemplazar el texto (pregunta abierta).
- Los datos de Darze que no estén configurados no se imprimen.

## 6. Fuera de alcance
- Enviar el PDF por correo, firma digital y logo en imagen.
- Texto de condiciones editable desde el sistema.

## 7. No funcionales
- Se genera al pedirlo, sin guardarlo. Mismo ReportLab y mismos estilos que la cotización (ADR 0004); sin dependencias nuevas.

## 8. Preguntas abiertas
- [ ] Darze debe revisar el texto de las condiciones y la política de cancelación (R-PDF-4).
