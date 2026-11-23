# Dominio — Darze (catering y organización de eventos)

> Fuente de verdad del negocio. Se basa en el documento del proyecto validado por Darze (reglas RN01–RN33, requisitos RF01–RF104 e historias HU01–HU43). Lo marcado **(por validar)** son supuestos: preguntar al humano antes de implementarlos. Lo marcado **(provisional)** lo decidió el equipo y se informó al Product Owner: se aplica hasta que Darze diga otra cosa (ver §11).

## 1. El negocio
Darze es una empresa de **catering y organización de eventos** ubicada en San Juan de Lurigancho, Lima. Atiende matrimonios, eventos corporativos, cenas de gala y celebraciones **en el lugar que indica el cliente** (no tiene salones propios). Hoy registra su información en hojas de Excel; el sistema la centraliza en un solo flujo:

`cliente → cotización → contrato → evento → personal, materiales y compras → pagos y cierre`

## 2. Glosario
- **Cliente:** persona natural o jurídica que solicita un servicio. Se identifica por su documento (DNI o RUC), que es único.
- **Servicio:** ítem del catálogo (menú, bebidas, personal de atención, decoración, menaje, montaje…) con nombre, categoría, descripción, precio referencial, forma de cobro (**por persona** o **por unidad**) y estado.
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
6. Darze puede atender **varios eventos el mismo día y a la misma hora** (p. ej., en distintos pisos de un local). La cotización **no reserva** la fecha.
7. **Vigencia:** 15 días por defecto; el encargado puede cambiarla en cada cotización **(provisional)**.
8. **Códigos:** `COT-AAAA-NNNN`, `CON-AAAA-NNNN` y `EVT-AAAA-NNNN`; el correlativo se reinicia cada año **(provisional)**.
9. **Precios finales en soles, sin IGV aparte:** Darze no emite boletas ni facturas, solo registra pagos **(provisional)**.
10. Mientras la cotización está en **borrador**, el encargado puede cambiar el precio de una línea (negociación o promoción). Se guarda también el precio del catálogo. No hay un campo de descuento aparte **(provisional)**.
11. En los servicios **por persona**, la cantidad propuesta es el número de invitados y se puede editar **(provisional)**.
12. **Conceptos adicionales** (movilidad, recargos…): líneas libres con descripción y monto **(provisional)**.
13. **Tipos de evento:** lista fija: Matrimonio, Cumpleaños, Quinceañero, Corporativo, Promoción, Otro **(provisional)**.
14. Una cotización rechazada o vencida no se reabre: se crea una nueva **(provisional)**.
15. **HU10** (convertir en evento) se realiza a través del contrato: solo el contrato firmado y con el adelanto pagado se convierte en evento (RN07, RN08) **(provisional)**.

## 4.1 Reglas de clientes y catálogo
1. El cliente se registra con nombre, documento y teléfono; correo y **dirección son opcionales** (el evento tiene su propio lugar).
2. La búsqueda de clientes **no distingue tildes ni mayúsculas**: "Jose Ramirez" encuentra a "José Ramírez".
3. El personal (mozos, bartenders…) se cobra **por persona y por evento**. Las **horas extra** que pida el cliente se registran como un servicio aparte, por unidad (1 unidad = 1 hora).
4. **No se puede desactivar una categoría que tenga servicios activos**: primero se desactivan o se mueven sus servicios.
5. Dos servicios **pueden tener el mismo nombre** con precios distintos (p. ej., la misma temática en dos pisos).

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
| Pagos, ingresos y egresos | ✔ | ✔ | – |
| Productos, almacén, requerimientos y compras | ✔ | requerimientos | ✔ |
| Reportes financieros | ✔ | – | – |
| Agente de IA | ✔ | ✔ | ✔ |

Cada usuario tiene una cuenta personal (RN01). Se autoriza por **permiso** (p. ej. `quotes:create`), no por nombre de rol. Los registros con operaciones relacionadas no se eliminan: se desactivan (RN02). Correcciones y anulaciones guardan usuario, fecha, hora y motivo (RN03).

## 10. Preguntas abiertas para el negocio
1. ~~Política de cancelación y devolución del adelanto.~~ Resuelta: sin reglas automáticas (§11).
2. **Cotización de promoción:** se cobra el servicio más un precio **por asiento**; cada alumno tiene su mesa (mínimo 4 asientos) y puede pedir sillas extra con costo. Falta definir cómo se cotiza y se paga **por alumno**. Se tratará como una historia aparte, después de HU07.
3. Método de costeo de insumos.
4. ~~¿El encargado de eventos puede registrar pagos?~~ Resuelta: sí (§11).
5. ¿Hay servicios de cortesía (precio S/ 0)? Hoy el sistema los permite.

## 11. Registro de decisiones
| Fecha | Tema | Decisión | Fuente |
|---|---|---|---|
| 11/11/2026 | Dirección del cliente | Opcional | Product Owner |
| 11/11/2026 | Búsqueda de clientes | Sin distinguir tildes | Product Owner |
| 11/11/2026 | Cobro del personal | Por persona y evento; horas extra aparte | Product Owner |
| 11/11/2026 | Categoría con servicios activos | No se puede desactivar | Product Owner |
| 11/11/2026 | Eventos simultáneos y nombres repetidos | Se permiten | Product Owner |
| 11/11/2026 | Clientes, cotizaciones, contratos y eventos | Un solo módulo comercial (ADR 0003) | Product Owner |
| 15/11/2026 | Vigencia, códigos, IGV, precio editable, cantidad por persona, conceptos adicionales, tipos de evento, cotización vencida (§4, reglas 7–14) | Ver §4 | Equipo **(provisional)** |
| 15/11/2026 | Qué se convierte en evento | El contrato firmado con adelanto (§4, regla 15) | Equipo, según el documento validado **(provisional)** |
| 22/11/2026 | Contraseña de usuario | Mínimo 8 caracteres, sin exigir símbolos (R-ID-1) | Equipo **(provisional)** |
| 22/11/2026 | Intentos fallidos de inicio de sesión | Solo se registran en el historial; la cuenta no se bloquea (R-ID-2) | Equipo **(provisional)** |
| 22/11/2026 | Horario del evento | Puede cruzar la medianoche: si la hora de fin es menor que la de inicio, termina al día siguiente (R-COT-1) | Equipo **(provisional)** |
| 22/11/2026 | Cotización enviada | Para cambiarla se devuelve a borrador (R-COT-2) | Equipo **(provisional)** |
| 22/11/2026 | Estados de la cotización | Borrador → enviada, aceptada o rechazada; enviada → aceptada, rechazada o borrador; aceptada y rechazada son finales (R-COT-3) | Equipo **(provisional)** |
| 22/11/2026 | Fecha del evento | Hoy o una fecha futura (R-COT-4); al menos una línea por cotización (R-COT-5) | Equipo **(provisional)** |
| 22/11/2026 | PDF de la cotización | Solo se descarga una cotización enviada o aceptada; el orden es armar → marcar como enviada → descargar (R-PDF-1) | Equipo **(provisional)** |
| 22/11/2026 | Cancelación y devolución del adelanto | Sin reglas automáticas: el sistema registra la anulación con su motivo y, si hubo devolución, el monto, el usuario y la fecha (R-CON-3) | Product Owner |
| 22/11/2026 | ¿Quién registra pagos, firma y adelanto? | Administrador y encargado de eventos (R-CON-4; amplía el actor de HU42) | Product Owner |
| 22/11/2026 | Firma del contrato | La firma y el pago del adelanto se registran en un solo paso (R-CON-1); el adelanto es mayor que cero (R-CON-2); una cotización tiene un solo contrato (R-CON-5) | Equipo **(provisional)** |
| 22/11/2026 | ¿Cuándo nace el evento? | Con un botón **"Convertir en evento"** en el contrato firmado con adelanto, no automáticamente (R-EVT-1) | Product Owner |
| 22/11/2026 | Responsable de coordinación del evento | Un usuario del sistema (administrador o encargado de eventos) hasta que exista el módulo de personal (R-EVT-2) | Product Owner |
| 22/11/2026 | Anular un contrato que ya es evento | No se anula desde el contrato: se cancela el evento (R-EVT-3); también lo impide la base de datos | Equipo **(provisional)** |
| 23/11/2026 | Cancelar un evento | Cancelar el evento anula su contrato con el mismo motivo y registra la devolución si la hubo, en un solo paso (R-EVT-4). Para cambiar algo de un contrato firmado, se anula y se hace una cotización nueva | Scrum Master **(provisional, a validar por el Product Owner)** |
| 23/11/2026 | ¿Desde qué estado se cancela un evento? | Desde programado o confirmado; no desde en ejecución ni finalizado (R-EVT-5) | Equipo **(provisional)** |
| 22/11/2026 | Sesión | Termina tras 30 minutos sin actividad; no se puede desactivar al último administrador activo (R-ID-4) | Equipo, según HU01 **(provisional)** |
