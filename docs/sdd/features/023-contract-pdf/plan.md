# Plan: Contrato en PDF

- **Spec**: ./spec.md
- **Estado**: aprobado (César Suclupe, 26/11/2026)
- **ADR**: 0004 (sin dependencias nuevas)

## 1. Módulos y capas
- **Aplicación** (`commercial/application/contracts`):
  - puerto `ContractDocumentRenderer.render(document) -> bytes` y `ContractDocument` (contrato, cliente, cotización, datos de Darze, condiciones, fecha de emisión), junto a `CompanyProfile`;
  - caso de uso `GetContractDocument(contracts, quotes, clients, renderer, company, clock)`: rechaza un contrato anulado (`contract.pdf_not_available`) y devuelve `(CON-AAAA-NNNN.pdf, bytes)`. Solo lee.
  - `CONTRACT_TERMS`: cláusulas fijas (R-PDF-4).
- **Infraestructura**: `ReportLabContractRenderer` (`contract_pdf.py`), con `soles`, `_facts`, `_styles` y el encabezado de `quote_pdf.py`.
- **Presentación**: `GET /v1/contracts/{contract_id}/pdf` (`operationId: contracts_pdf`), `application/pdf` con `Content-Disposition: attachment`. 404 `contract.not_found`; 409 `contract.pdf_not_available`.

## 2. Contenido (A4)
1. Encabezado: Darze a la izquierda; "CONTRATO", código, emisión y estado a la derecha.
2. Cliente y evento (dos columnas).
3. Servicios: descripción, cantidad, precio, subtotal y total.
4. Montos: total, adelanto, saldo y fecha límite; si está firmado, "Firmado el … por …".
5. Condiciones y política de cancelación.
6. Firmas: cliente y Darze.

## 3. Tests
- **Unit**: arma el documento; rechaza anulado; acepta pendiente y firmado; no cambia el contrato; el renderer lleva código, cliente, montos, condiciones y firmante.
- **API**: tipo, nombre, 404, 409, 403 para compras.
- **Integración**: descarga con PostgreSQL.

## 4. Frontend
Botón "Descargar PDF" en el detalle del contrato (como el de cotización), deshabilitado si está anulado.

## 5. Documentación
`DOMAIN.md` §11 (R-PDF-2 a R-PDF-4) y `openapi.json`.
