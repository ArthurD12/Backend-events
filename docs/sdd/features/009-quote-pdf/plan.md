# Plan: Cotización en PDF

- **Spec**: ./spec.md
- **Estado**: borrador (pendiente de aprobación)
- **ADR**: 0004

## 1. Módulos y capas
- **Aplicación** (`commercial/application/quotes`):
  - puerto `QuoteDocumentRenderer.render(document) -> bytes`;
  - caso de uso `GetQuoteDocument(quotes, clients, renderer, company, clock)`, que arma un `QuoteDocument` (cotización, cliente, datos de Darze, fecha de emisión y estado efectivo) y devuelve `(nombre_de_archivo, bytes)`. Solo lee: no llama a `update`.
- **Infraestructura**: `ReportLabQuoteRenderer` (A4, tablas y montos alineados) y `CompanySettings` (variables `COMPANY_*`, todas opcionales; `COMPANY_NAME` vale "Darze" por defecto).
- **Presentación**: `GET /v1/quotes/{quote_id}/pdf` (`operationId: quotes_pdf`) con el permiso `quotes:manage`. Responde `application/pdf` con `Content-Disposition: attachment; filename="COT-AAAA-NNNN.pdf"`. 404 si no existe.

## 2. Contenido del PDF (A4)
1. **Encabezado**: datos de Darze configurados, a la izquierda; a la derecha "COTIZACIÓN", el código, la fecha de emisión, la vigencia y la marca BORRADOR o VENCIDA si corresponde.
2. **Cliente**: nombre, documento, teléfono y correo.
3. **Evento**: tipo, fecha, horario ("20:00 a 03:00 del día siguiente"), lugar e invitados.
4. **Detalle**: tabla con descripción (servicio o concepto), cantidad, precio unitario y subtotal.
5. **Total** destacado y "Precios en soles. No incluye IGV aparte."
6. **Notas** (si hay) y pie "Cotización válida hasta …".

## 3. Tests
- **Unit**: el caso de uso arma el documento correcto (estado efectivo, cliente, fecha de emisión) y no cambia la cotización; el renderer produce un PDF válido (`%PDF`) y, generado sin compresión, contiene el código, el total, el cliente y la marca BORRADOR.
- **API**: tipo `application/pdf`, nombre del archivo, 404 y permisos (compras → 403). El estado sigue igual después de descargar.
- **Integración**: descarga de punta a punta con PostgreSQL.

## 4. Frontend (repo `frontend-events`)
Botón **"Descargar PDF"** en el detalle de la cotización: pide el archivo con el token (como `Blob`) y lo descarga con el nombre del código.

## 5. Documentación
`STACK.md`, `README.md` e `INSTALACION.md` (dependencia nueva), `.env.example` (`COMPANY_*`) y `openapi.json`.
