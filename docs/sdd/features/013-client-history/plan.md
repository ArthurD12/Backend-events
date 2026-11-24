# Plan: Historial del cliente

- **Spec**: ./spec.md
- **Estado**: borrador, pendiente de aprobación

## 1. Módulos y fronteras
- Solo `commercial`. Sin tablas nuevas ni migraciones.
- Lee los repositorios existentes: cotizaciones (`QuoteFilters.client_id` ya existe), contratos y eventos (se agrega el filtro `client_id`).

## 2. Caso de uso
| Caso de uso | Entrada | Errores (`code`) |
|---|---|---|
| `ClientHistory` | `client_id` | `client.not_found` (404) |

Devuelve:
- el cliente (nombre, documento, activo);
- las cotizaciones (id, código, fecha del evento, tipo, total, estado efectivo);
- los eventos (id, código, fecha, tipo, total del contrato, estado);
- el resumen de R-HIS-1.

## 3. API
| Método y ruta | `operationId` | Permiso |
|---|---|---|
| `GET /v1/clients/{id}/history` | `clients_history` | `clients:manage` |

## 4. Frontend
- Página **`/clientes/[id]`** (perfil del cliente):
  - arriba, sus datos y el resumen (4 tarjetas);
  - debajo, pestañas **Cotizaciones** y **Eventos** con tabla de código, fecha, tipo, importe y estado, y cada fila enlazada a su detalle;
  - en celular, las tablas se ven como lista.
- En la lista de clientes, el nombre pasa a ser un enlace al perfil.

## 5. Tests
- **Unit**: historial con cotizaciones en varios estados (incluida vencida), contrato firmado y anulado (el total contratado no cuenta el anulado), evento cancelado; cliente inexistente; permisos (compras recibe 403).
- **Integración**: la consulta por cliente en PostgreSQL real (no mezcla clientes).
- **Navegador**: pestañas, enlaces, resumen y celular.

## 6. Riesgos
- Bajo: solo lectura, sin datos sensibles nuevos.
