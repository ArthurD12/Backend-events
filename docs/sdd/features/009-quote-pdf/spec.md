# Spec: Cotización en PDF

- **ID**: 009-quote-pdf
- **Estado**: borrador (pendiente de aprobación)
- **Módulos afectados**: `commercial` (cotizaciones)
- **Historia**: HU09 (#10)

## 1. Problema y objetivo
La cotización ya se arma en el sistema, pero al cliente hay que entregarle un documento. Hoy se copiaría a mano a Word o Excel, con riesgo de errores. El objetivo es descargar un PDF profesional, generado desde lo registrado, listo para enviar o imprimir.

## 2. Actores
- **Encargado de eventos** y **administrador** (permiso `quotes:manage`).

## 3. Historia
- **HU09**: Como encargado de eventos, quiero generar la cotización en PDF, para entregarla o enviarla al cliente.

## 4. Criterios de aceptación
- **CA-09.1**: El PDF muestra los datos de Darze (los configurados en `.env`) y los del cliente: nombre, documento, teléfono y correo.
- **CA-09.2**: Incluye el código, la fecha de emisión, la vigencia, los datos del evento (tipo, fecha, horario —indicando si termina al día siguiente—, lugar e invitados), las líneas (descripción, cantidad, precio y subtotal) y el total.
- **CA-09.3**: La información coincide con la cotización registrada: los montos salen de la cotización guardada, no se recalculan con el catálogo actual.
- **CA-09.4**: Se descarga como archivo `COT-AAAA-NNNN.pdf` y se puede imprimir.
- **CA-09.5**: Generar el PDF no cambia el estado ni ningún dato de la cotización.

## 5. Reglas
- Precios en soles, sin IGV aparte (DOMAIN.md §4, regla 9): el PDF lo dice.
- Una cotización en **borrador** se puede descargar, pero el PDF lleva la marca **"BORRADOR"**, para que no se entregue por error una propuesta sin terminar. Una **vencida** lleva **"VENCIDA"**.
- Los datos de Darze que no estén configurados no se imprimen: nunca se inventan.

## 6. Fuera de alcance
- Enviar el PDF por correo desde el sistema.
- Logo en imagen (hasta tener el logo real) y pantalla "Configuración".
- PDF de contratos y comprobantes (otras historias).

## 7. No funcionales
- Se genera al pedirlo, en menos de un segundo para una cotización normal. No se guarda.
- Dependencia nueva aprobada en ADR 0004.

## 8. Preguntas abiertas
- [x] ¿Librería? → ReportLab (César, 22/11/2026).
- [x] ¿Dónde se configuran los datos de Darze? → `.env` por ahora (César, 22/11/2026).
- [ ] Datos reales de Darze (RUC, dirección, teléfono, correo) para cargarlos en el `.env` de la instalación.
