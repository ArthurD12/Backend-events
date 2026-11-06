# Dominio — Darze (catering y organización de eventos)

> Fuente de verdad del negocio. Se basa en el documento del proyecto validado por Darze (reglas RN01–RN33, requisitos RF01–RF104 e historias HU01–HU43). Lo marcado **(por validar)** son supuestos: preguntar al humano antes de implementarlos.

## 1. El negocio
Darze es una empresa de **catering y organización de eventos** ubicada en San Juan de Lurigancho, Lima. Atiende matrimonios, eventos corporativos, cenas de gala y celebraciones **en el lugar que indica el cliente** (no tiene salones propios). Hoy registra su información en hojas de Excel; el sistema la centraliza en un solo flujo:

`cliente → cotización → contrato → evento → personal, materiales y compras → pagos y cierre`

## 2. Glosario
- **Cliente:** persona natural o jurídica que solicita un servicio. Se identifica por su documento (DNI o RUC), que es único.
- **Servicio:** ítem del catálogo (menú, bebidas, personal de atención, decoración, menaje, montaje…) con nombre, categoría, descripción, precio referencial y estado.
- **Cotización:** propuesta económica para un cliente: tipo de evento, fecha, horario, lugar, invitados, servicios con cantidades y precios, total y **vigencia**.
- **Contrato:** formaliza una cotización aceptada. Copia sus datos sin permitir editarlos, fija el **adelanto pactado** y la **fecha límite del saldo**, y registra la firma.
- **Evento:** el servicio programado que se ejecuta en una fecha, horario y lugar. Nace de un contrato firmado.
- **Trabajador:** persona que cumple una función en un evento (cocinero, mozo, ayudante, coordinador…).
- **Asignación:** un trabajador asignado a un evento, con función, horario y pago acordado.
- **Producto:** insumo, material o utensilio del almacén, con unidad de medida y stock mínimo.
- **Requerimiento:** cálculo de los materiales que necesita un evento, comparado con el stock para identificar faltantes.
- **Compra:** adquisición a un **proveedor** a partir de los faltantes; incrementa el stock solo al recibirse.
- **Movimiento:** registro inmutable de dinero (ingreso, egreso, anulación) o de almacén (entrada, salida, devolución, merma).

## 3. Ciclos de vida
- **Cotización:** `borrador → enviada → aceptada | rechazada | vencida`. Solo se edita en borrador (RN05). Vence al terminar su vigencia sin ser aceptada (RN06).
- **Contrato:** `pendiente de firma → firmado | anulado`. Solo se genera desde una cotización aceptada y sin contrato previo (HU41). Un contrato firmado no se edita; la anulación exige motivo (HU42).
- **Evento:** `programado → confirmado → en ejecución → finalizado` · `cancelado`. Solo un contrato firmado y con el adelanto pagado se convierte en evento, y una sola vez (RN07, RN08, HU42).

## 4. Reglas de cotizaciones, contratos y eventos
1. Cada cotización, contrato y evento tiene un **código único** generado por el sistema (RN04).
2. Los precios se **congelan en la cotización**: cambiar el catálogo no altera cotizaciones, contratos ni eventos existentes. Solo se seleccionan servicios activos.
3. El **adelanto pactado** es el 50 % del total por defecto y puede ajustarse al generar el contrato. La **fecha límite del saldo** es 7 días antes del evento (HU41).
4. Todo evento tiene cliente, fecha, horario, lugar, cantidad de invitados y responsable de coordinación (RN09).
5. Cancelar un evento no elimina sus cotizaciones, pagos, gastos ni movimientos (RN10).
6. ¿La cotización reserva la fecha del evento? **(por validar)**.

## 5. Personal y asignaciones
1. Solo se asignan trabajadores **activos y disponibles** (RN11).
2. Un trabajador **no puede tener dos asignaciones con horarios que se superpongan** (RN12). Se garantiza con una restricción de exclusión en PostgreSQL, no solo en el código.
3. Toda asignación indica evento, función, horario y pago acordado (RN13).

## 6. Dinero (pagos y flujo de caja)
- Moneda `PEN`, enteros en céntimos. Sin pasarela: los cobros se **registran** (efectivo, transferencia, tarjeta, Yape/Plin) con referencia y usuario.
- El importe de un pago es mayor que cero y no supera el saldo pendiente (RN14). **Saldo = total contratado − pagos + anulaciones** (RN15).
- El adelanto se registra desde el contrato (HU42) y se guarda como **el primer pago del evento**; los pagos parciales posteriores se registran en el módulo de pagos (HU19).
- Todo ingreso o egreso registra fecha, concepto, monto y usuario (RN16). Los egresos se clasifican (insumos, personal, transporte, otros) y pueden asociarse a un evento.
- **Append-only:** un pago o movimiento no se elimina; se anula con una operación autorizada que conserva el historial (RN17).

## 7. Almacén, requerimientos y compras
- Todo movimiento indica producto, cantidad (> 0), fecha, tipo y usuario (RN18, RN19). Movimientos **append-only**; stock = suma de movimientos.
- Una salida no supera el stock disponible (RN20). Las salidas para un evento quedan asociadas a él (RN22). Devoluciones y mermas actualizan el stock (RN23); toda merma registra su motivo (RN24).
- Alertas de **stock mínimo** y de **vencimiento próximo** (RN25).
- Los **requerimientos** se calculan según el menú, los servicios y la cantidad de invitados (RN26), a partir de los insumos definidos por menú o servicio (HU24).
- Una compra pasa por `solicitada → ordenada → recibida | cancelada` y solo incrementa el stock al estar **recibida** (RN21).
- Método de costeo de insumos (promedio ponderado o por lote) **(por validar)**.

## 8. Agente de inteligencia artificial
- Solo lo usan usuarios autenticados (RN27) y solo consulta información autorizada para su rol (RN28).
- Accede a los datos mediante **funciones controladas del backend**, nunca con conexión directa a la base de datos (RN29).
- En la primera versión es **solo de consulta**: no registra, modifica, aprueba, anula ni elimina nada (RN30).
- Ante una consulta ambigua pide aclaración (RN31); si no hay datos suficientes lo dice y no inventa (RN32).
- Toda consulta queda registrada para auditoría: usuario, fecha, pregunta, funciones ejecutadas y respuesta (RN33).

## 9. Roles y permisos
| Capacidad | Administrador | Encargado de eventos | Encargado de compras y almacén |
|---|:-:|:-:|:-:|
| Usuarios, roles e historial de accesos | ✔ | – | – |
| Catálogo de servicios | ✔ | lectura | lectura |
| Clientes | ✔ | ✔ | – |
| Cotizaciones y contratos | ✔ | ✔ | – |
| Eventos, personal y asignaciones | ✔ | ✔ | lectura |
| Pagos, ingresos y egresos | ✔ | **(por validar)** | – |
| Productos, almacén, requerimientos y compras | ✔ | requerimientos | ✔ |
| Reportes financieros | ✔ | – | – |
| Agente de IA | ✔ | ✔ | ✔ |

Cada usuario tiene una cuenta personal (RN01). Se autoriza por **permiso** (p. ej. `quotes:create`), no por nombre de rol. Los registros con operaciones relacionadas no se eliminan: se desactivan (RN02). Correcciones y anulaciones guardan usuario, fecha, hora y motivo (RN03).

## 10. Preguntas abiertas para el negocio
1. Política de cancelación y devolución del adelanto.
2. ¿Quién puede dar descuentos y hasta qué porcentaje?
3. ¿La cotización reserva la fecha mientras está vigente?
4. Método de costeo de insumos.
5. ¿El encargado de eventos puede registrar pagos?
