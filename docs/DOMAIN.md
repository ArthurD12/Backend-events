# Dominio — Local de eventos

> Fuente de verdad del negocio. Lo marcado **(por validar)** son supuestos: preguntar al humano antes de implementarlos.

## 1. El negocio
Un edificio con varios salones (uno por piso). Se realizan matrimonios, cumpleaños y promociones. Todo está en el local: salones, cocina, barra y almacén. Un solo punto de venta. Todo lo que se vende está **ligado a una reserva**; la venta ocasional de cerveza se registra como ingreso manual (ver §6).

## 2. Glosario
- **Salón (venue):** espacio rentable. Uno por piso, **no divisible**. Tiene capacidad, tarifa por hora y tiempos de montaje/limpieza.
- **Reserva (booking):** uso de un salón en un rango de horas para un cliente. Es el eje del sistema.
- **Paquete:** oferta cerrada **Normal / Pro / Premium** con composición fija (p. ej. 100 personas, 3 mozos, 3 tipos de comida, 1 anfitriona, 1 bartender).
- **Servicio:** ítem contratable con unidad de cobro: por hora (bartender extra), por persona, por unidad (torta, camarógrafo) o por evento.
- **Evento personalizado:** reserva sin paquete (o con paquete + modificaciones), armada por ítems: horas del salón, cantidad de bartenders y horas, comida, mozos, anfitrionas, tipo de torta, camarógrafos, etc.
- **Insumo:** producto **perecible o consumible** del evento (barra, cocina, evento: champán, etc.). Los equipos y mobiliario NO se controlan en el sistema.
- **Lote:** entrada de un insumo con cantidad, costo y fecha de vencimiento.
- **Movimiento (ledger):** registro inmutable de ingreso, egreso, ajuste o reversión de dinero.

## 3. Ciclo de vida de una reserva
`cotizada → reservada (con adelanto) → confirmada → realizada → cerrada` · `cancelada` (desde cualquier estado previo a realizada).
- Una **cotización** no bloquea el salón (por validar: ¿bloqueo temporal con vencimiento?).
- Al **reservar** se congelan precios y se bloquea el rango de horas del salón.
- Al **cerrar** se concilian cobros, consumo real de insumos y rentabilidad.

## 4. Reglas de reserva
1. Rango por horas + **tiempo de montaje/limpieza** (buffer) por salón. El bloqueo real es `[inicio - montaje, fin + limpieza]`.
2. Dos reservas activas no pueden solaparse en el mismo salón. Se garantiza con `EXCLUDE USING gist` sobre `tstzrange` (ver skill `db-migrations`).
3. Una reserva **cancelada** libera el rango. Política de cancelación y penalidades: **(por validar)**.
4. Cambiar fecha/horas = reprogramar con la misma validación de solape.

## 5. Paquetes, servicios y precios
- Un paquete define: personas incluidas, cantidades por servicio incluido, tipos de comida y su **receta de consumo estimado de insumos** (para planificar el stock).
- Personas adicionales, horas extra y servicios extra se cobran aparte según su unidad.
- **Snapshot de precios:** cada ítem de la reserva guarda nombre, cantidad, unidad y precio unitario al momento de reservar. Cambios posteriores del catálogo no afectan reservas existentes.
- Descuentos: quién puede darlos y hasta cuánto **(por validar)**.

## 6. Dinero (ledger)
- Moneda `PEN`, enteros en céntimos. Sin pasarela: los cobros se **registran** (efectivo, transferencia, Yape/Plin, otro) con referencia y quién lo registró.
- Adelanto, cuotas y saldo son movimientos ligados a la reserva. **Saldo pendiente = total contratado − cobros + reversiones.**
- Append-only: un error se corrige con un movimiento de **reversión**, nunca editando ni borrando.
- Egresos operativos (compras, pagos a personal/terceros) también se registran, con categoría y, si aplica, la reserva a la que pertenecen.
- **Venta ocasional de cerveza:** ingreso manual con categoría `venta_bebida`, sin módulo de ventas.

## 7. Inventario (solo perecibles y consumibles del evento)
- Ubicaciones lógicas: **barra, cocina, evento** (por validar si se requiere ubicación física más fina).
- Movimientos append-only: entrada (compra), salida por **consumo de evento**, merma, ajuste. Stock = suma de movimientos.
- Salida de lotes por **FEFO** (primero el que vence antes). Alertas de vencimiento próximo y de stock mínimo.
- Consumo **estimado** (según paquete/personas) vs **real** (registrado al cerrar): la diferencia alimenta mermas y costos.
- La cerveza puede existir como insumo con stock; su venta no se gestiona aquí.

## 8. Rentabilidad por evento
`ingresos de la reserva − costo de insumos consumidos − costo de servicios (personal propio o terceros) − otros egresos asociados`.
Costeo de insumos: **(por validar: promedio ponderado o PEPS/FEFO por lote)**; el costo se **congela en cada salida**. Costo de personal/terceros por servicio: **(por validar)**.

## 9. Roles y permisos (propuesta, por validar)
| Capacidad | Administrador | Vendedor | Almacén |
|---|:-:|:-:|:-:|
| Usuarios y roles | ✔ | – | – |
| Catálogo y precios | ✔ | lectura | lectura (insumos ✔) |
| Clientes | ✔ | ✔ | – |
| Cotizar y reservar | ✔ | ✔ | lectura |
| Registrar cobros de una reserva | ✔ | ✔ | – |
| Reversiones y egresos | ✔ | – | – |
| Inventario (entradas, mermas, consumo) | ✔ | – | ✔ |
| Reportes y rentabilidad | ✔ | – | – |
| Conector del servicio de IA | ✔ | – | – |
El administrador ve y hace todo. Se autoriza por **permiso** (p. ej. `bookings:create`), no por nombre de rol.

## 10. Datos que se exponen al servicio de IA (`reporting`)
Reservas y sus ítems (con precios congelados), movimientos del ledger (con categoría y reserva), movimientos de inventario con costo, y catálogo. Siempre por vistas versionadas de solo lectura; sin datos personales si no son necesarios.

## 11. Preguntas abiertas para el negocio
1. Política de cancelación y devolución de adelantos.
2. ¿Quién puede dar descuentos y hasta qué porcentaje?
3. ¿El personal (mozos, bartenders, anfitrionas, camarógrafos) es propio o contratado por evento? ¿Se registra su costo?
4. ¿La cotización bloquea el salón por un tiempo?
5. Método de costeo de insumos.
6. ¿Se necesita acceso desde el celular? (afecta solo al frontend).
