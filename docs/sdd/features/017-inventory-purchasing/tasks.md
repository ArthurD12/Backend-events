# Tasks: Inventario, movimientos de almacén, proveedores y compras

- [ ] T-01 [commercial] `commercial.public_api.event_lookup` (id, código, estado, fecha, horario) + tests
- [ ] T-02 [identity] Permisos `inventory:manage`, `inventory:read`, `purchasing:manage` + tests
- [ ] T-03 [inventory/domain+app] Producto, movimientos, `StockLevel`, `EventMaterials`, casos de uso + tests con fakes
- [ ] T-04 [inventory/infra] ORM, repos, `inventory_stock` con FOR UPDATE, trigger append-only, migración + integración
- [ ] T-05 [inventory/presentation] Rutas + tests de API + `just openapi`
- [ ] T-06 [purchasing/domain+app] Proveedor, compra y transiciones, faltantes + tests con fakes
- [ ] T-07 [purchasing/infra+presentation] ORM, migración, `stock_receiver` al recibir, rutas + integración + `just openapi`
- [ ] T-08 [docs] DOMAIN.md §7, §10.3 y §11 (R-INV-1..5, R-COM-1..2)
- [ ] T-09 [frontend] Almacén, materiales del evento, compras
