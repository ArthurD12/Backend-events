# ADR 0004 — PDF de cotizaciones con ReportLab

- **Estado:** aceptada por el equipo (22/11/2026)
- **Contexto:** ADR 0001 dejó fuera la generación de PDF ("no requerido"). HU09 (#10) la exige: la cotización se entrega al cliente en un PDF que coincide con lo registrado. La regla 11 de AGENTS.md pide un ADR para cualquier dependencia nueva.

## Decisiones
| Tema | Decisión | Motivo |
|---|---|---|
| Librería | `reportlab` | La nombra la propia HU09. Es Python puro con wheels para Windows, Linux y Docker: no necesita librerías del sistema. Es la más usada y estable |
| Descartadas | WeasyPrint (necesita GTK/Pango; en Windows es difícil de instalar); xhtml2pdf (se apoya en ReportLab con menos control); generar el PDF en el navegador (no garantiza que el documento coincida con la cotización guardada) | Mínimo mantenimiento e instalación sencilla para el equipo y para Darze |
| Dónde | En `commercial/infrastructure`, detrás de un puerto `QuoteDocumentRenderer` | El dominio y la aplicación no dependen de la librería; se podría cambiar sin tocar las reglas |
| Datos de Darze | Variables `COMPANY_*` en `.env` (nombre, RUC, dirección, teléfono, correo). Las que falten no se imprimen | Cambian muy poco. Una pantalla "Configuración" puede reemplazarlas después |
| Logo | Por ahora el PDF lleva el nombre comercial en texto, sin imagen | El logo real de Darze todavía no está disponible |

## Consecuencias
- Una dependencia más en `pyproject.toml` (`reportlab`, que trae `pillow`), documentada en `STACK.md`, `README.md` e `INSTALACION.md` (regla 13).
- `types-reportlab` solo en desarrollo: ReportLab no trae tipos y mypy corre en modo estricto.
- El PDF se genera al pedirlo: no se guarda en disco ni en la base, y no cambia la cotización.
