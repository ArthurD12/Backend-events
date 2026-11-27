# Spec: Datos del personal (trabajadores)

- **ID**: 032-staff
- **Estado**: aprobado (24/11/2026)
- **Módulos afectados**: `staff` (nuevo), `identity` (permiso nuevo)
- **Historia**: HU15 (#16)


> **Actualización del 27/11/2026 (feature 025, aprobada por el Product Owner a partir de la aclaración del cliente):** el encargado de eventos es de ventas y **ya no tiene `staff:manage`**: no ve datos de trabajadores, asignaciones ni pagos, y recibe 403 en estas rutas. Solo ve el personal designado de un evento (nombre y función) con `staff_roster:read`. Donde este documento diga que el encargado de eventos accede, prevalece `docs/sdd/features/025-sales-staff-permissions/spec.md` y DOMAIN.md §9 y §11.

## 1. Problema y objetivo
Hoy Darze lleva a su personal (cocineros, mozos, bartenders, ayudantes, coordinadores) en hojas de Excel: no hay una lista confiable de quién trabaja con la empresa, el mismo documento se registra escrito de varias formas y, cuando alguien deja de trabajar, sus datos se borran y con ellos el registro de los eventos en los que participó.

El objetivo es tener un **registro único de trabajadores** con sus datos de contacto, función y tarifa referencial, que se pueda consultar y actualizar, y del que se pueda dar de baja a un trabajador **sin perder su historial**. Esta feature entrega la base sobre la que después se asignará personal a los eventos (HU17).

## 2. Actores
- **Administrador**: registra, consulta, modifica, activa y desactiva trabajadores.
- **Encargado de eventos**: también registra, consulta, modifica, activa y desactiva trabajadores. En el negocio se le llama **"vendedor"**: es el mismo rol, no uno nuevo.
- **Encargado de compras y almacén**: **sin acceso** al módulo de personal, ni siquiera de lectura (decisión de negocio 24/11/2026; coherente con DOMAIN.md §9, fila «Personal (trabajadores)»).
- **Trabajador**: *no* es usuario del sistema. No inicia sesión, no consulta ni edita sus datos; sus cuentas de acceso serían otra historia (identity).

## 3. Historia
- **HU15**: Como administrador, quiero registrar y mantener los datos del personal para controlar a los trabajadores disponibles para los eventos.

> La HU habla de "trabajadores disponibles": aquí solo se deja el estado **activo / inactivo**. La disponibilidad real y la asignación a eventos son HU17.

## 4. Criterios de aceptación
- **CA-15.1**: Dado un usuario autorizado, cuando registra un trabajador con **nombre** y **documento** (tipo + número), entonces queda guardado, es consultable y figura como **activo** desde el inicio; el teléfono y la tarifa son opcionales.
- **CA-15.2**: Dado un alta sin nombre o sin documento (o sin su tipo), cuando se intenta guardar, entonces se rechaza y no se registra nada.
- **CA-15.3**: Dado que ya existe un trabajador —activo o **inactivo**— con la combinación **tipo + número** «X» (ya normalizada), cuando se intenta registrar otro trabajador con esa misma combinación, entonces se rechaza con un mensaje que identifica el documento duplicado y no se crea el registro; un DNI y un CE con el mismo número sí pueden coexistir.
- **CA-15.4**: Dado un trabajador existente, cuando se edita su documento a la combinación **tipo + número** de otro trabajador, entonces se rechaza igual que CA-15.3 y la ficha conserva su documento anterior.
- **CA-15.5**: Dado dos altas simultáneas con la misma combinación **tipo + número**, entonces solo una queda registrada; la otra se rechaza por documento duplicado (no quedan dos fichas con la misma combinación).
- **CA-15.6**: Dado un trabajador existente, cuando el usuario autorizado modifica nombre, teléfono, función, tipo, tarifa, la marca de hora extra o el monto de hora extra, entonces los datos nuevos se ven en la ficha y el cambio queda registrado con usuario y fecha-hora.
- **CA-15.7**: Dado un trabajador existente, cuando se consulta su ficha, entonces se ven todos sus datos y su estado (activo o inactivo), aunque esté inactivo.
- **CA-15.8**: Dado un conjunto de trabajadores, cuando se listan, entonces se puede filtrar por **función** y por **estado**, buscar por **nombre o documento** y el resultado llega **paginado**; los inactivos aparecen cuando el filtro los incluye.
- **CA-15.9**: Dado un trabajador activo, cuando el usuario autorizado lo desactiva, entonces queda inactivo, su ficha sigue existiendo y consultándose, y la baja registra usuario y fecha-hora; el **motivo es opcional**.
- **CA-15.10**: Dado un trabajador inactivo, cuando el usuario autorizado lo reactiva, entonces vuelve a estar activo y queda disponible para futuras asignaciones.
- **CA-15.11**: Dado cualquier trabajador (activo o inactivo), no existe ninguna operación —ni en la interfaz ni en la API— que lo elimine: los datos y su historial se conservan siempre (RN02).
- **CA-15.12**: Dado un trabajador inactivo, su estado se puede consultar desde fuera del módulo de personal, de modo que la asignación a eventos (HU17) pueda rechazarlo (RN11). HU15 no crea asignaciones.
- **CA-15.13**: Dado un trabajador inactivo cuya baja ya ocurrió, cuando se consulta su historial de eventos (cuando exista, HU17), entonces se sigue viendo completo: la baja es lógica.
- **CA-15.14**: Dado un usuario que no es administrador ni encargado de eventos, cuando intenta registrar, listar, ver la ficha, modificar, activar o desactivar, entonces se le deniega el acceso y no se modifica nada.
- **CA-15.15**: Dado un dato inválido (tipo de documento distinto de DNI o CE, documento que no cumple el formato tras normalizar —DNI de 8 dígitos; CE de 9 a 12 dígitos—, teléfono con caracteres que no son dígitos, tarifa negativa, tipo fuera de `fijo|eventual`, función fuera de la lista, o monto de hora extra inválido según CA-15.21), cuando se intenta guardar, entonces se rechaza con un mensaje claro y no se guarda parcialmente.
- **CA-15.16**: Todo alta, edición, activación y desactivación guarda **quién** lo hizo y **cuándo** (RN03).
- **CA-15.17**: Dado un alta o edición de trabajador, cuando se elige el tipo de trabajador, entonces solo se admiten **`fijo`** o **`eventual`**; no se registra ninguna distinción interno/externo.
- **CA-15.18**: Dado un trabajador, cuando se informa su función, entonces esta sale de una **lista fija del sistema** (cocinero, mozo, bartender, ayudante, coordinador) más **"otro"**; si la función es "otro", exige una **descripción breve obligatoria** de la función real (CA-15.25). Si después se cambia, el cambio queda auditado y la asignación de eventos conserva la función con la que se trabajó (RN13, HU17).
- **CA-15.19**: Dado un documento con espacios o guiones, cuando se guarda, entonces se **normaliza** quitándolos y se compara **por tipo + número** contra todos los trabajadores, **incluidos los inactivos**. El formato es: **DNI de 8 dígitos**; **CE solo dígitos, entre 9 y 12**.
- **CA-15.20**: Dado un trabajador con tarifa informada, cuando se guarda, entonces la tarifa es un importe en **céntimos de sol (`PEN`) por evento**, y su ausencia no impide guardar la ficha.
- **CA-15.21**: Dado un trabajador, cuando se marca que **aplica hora extra**, entonces exige un **monto referencial por hora extra mayor que cero**; cuando **no aplica**, entonces no admite monto de hora extra y el valor guardado es "sin monto". El monto es variable y puede ajustarse en cada asignación (HU17).
- **CA-15.22**: Dado un teléfono informado, cuando se guarda, entonces contiene **solo dígitos**, **sin longitud fija**; si se deja vacío, la ficha se guarda igual.
- **CA-15.23**: Dado un encargado de compras y almacén, cuando intenta cualquier operación del módulo de personal (incluida la lectura del listado o de una ficha), entonces se le deniega el acceso; el personal solo lo gestionan administrador y encargado de eventos.
- **CA-15.24**: Dado un trabajador reactivado, cuando se consulta su ficha, entonces se ve activo y la reactivación registra **usuario y fecha-hora**, con el mismo tratamiento de auditoría que la baja.
- **CA-15.25**: Dado un trabajador con función **"otro"**, cuando se guarda, entonces exige una **descripción breve obligatoria** de la función real; con cualquier otra función, la ficha **no admite** descripción y se guarda sin ella.

## 5. Reglas
- **R-STF-1** *(HU15; negocio, 24/11/2026)*: el **documento** identifica al trabajador y es **único por tipo + número** —nunca por número solo—, también entre los trabajadores **inactivos**. Se guarda con su **tipo** (DNI o carné de extranjería, CE) y se **normaliza** quitando espacios y guiones. Formato: **DNI de 8 dígitos**; **CE solo dígitos, entre 9 y 12**.
- **R-STF-2** *(HU15)*: la baja es **lógica** (cambio de estado), nunca borrado físico; se aplica para no romper la integridad referencial con el historial de eventos.
- **R-STF-3** *(HU15)*: desactivar **no elimina** el historial de eventos del trabajador.
- **R-STF-4** *(DOMAIN.md §5, RN11)*: solo se asignan trabajadores **activos y disponibles**. En esta historia se garantiza el estado; el rechazo al asignar lo aplica HU17.
- **R-STF-5** *(DOMAIN.md §9; negocio, 24/11/2026)*: la autorización es por **permiso** ligado a una capacidad, no por nombre de rol; el acceso al personal exige el permiso `staff:manage` en `identity`. Lo tienen administrador y encargado de eventos; el encargado de compras y almacén **no lo tiene**.
- **R-STF-6** *(DOMAIN.md §9, RN02 y RN03)*: los registros con operaciones relacionadas no se eliminan, se desactivan; correcciones, altas, activaciones y bajas guardan usuario, fecha y hora (el motivo, solo si se informa).
- **R-STF-7** *(DOMAIN.md §2 y §5)*: la **tarifa referencial** no es el pago. El pago acordado se fija en cada asignación (RN13, HU17); cambiar la tarifa de un trabajador no altera asignaciones ni pagos ya acordados.
- **R-STF-8** *(DOMAIN.md §4.1, regla 3; negocio, 24/11/2026)*: la tarifa es **por evento**, en céntimos de sol (`PEN`), **opcional y referencial**. La ficha indica si **aplica hora extra** y, solo en ese caso, un **monto referencial por hora extra**, que es **variable** y puede ajustarse en cada asignación (HU17); el pago real se acuerda ahí.
- **R-STF-9** *(equipo, provisional)*: dos trabajadores pueden tener el mismo nombre; los distingue el documento.
- **R-STF-10** *(equipo, provisional)*: todo trabajador nuevo queda **activo** al registrarse; no se registra directamente como inactivo.
- **R-STF-11** *(negocio, 24/11/2026)*: el **tipo de trabajador** solo admite `fijo` o `eventual`. Todos forman parte del proceso interno de Darze; **no se registra** la distinción interno/externo.
- **R-STF-12** *(negocio, 24/11/2026; RN13, HU17)*: la **función** es una **lista fija del sistema** (cocinero, mozo, bartender, ayudante, coordinador) más **"otro"**; con "otro" se exige una **descripción breve** de la función real, y con las demás no se registra descripción (R-STF-17). Es editable después con auditoría, y la asignación conserva la función con la que se trabajó ese evento.
- **R-STF-13** *(negocio, 24/11/2026)*: los únicos datos **obligatorios** son **nombre y documento** (tipo + número). Teléfono y tarifa son opcionales; el teléfono, si se informa, admite **solo dígitos**, sin longitud fija.
- **R-STF-14** *(negocio, 24/11/2026)*: la **hora extra es condicional**: si la ficha marca que **aplica**, el monto referencial por hora extra es mayor que cero; si **no aplica**, no corresponde monto.
- **R-STF-15** *(negocio, 24/11/2026)*: se permite **reactivar** a un trabajador inactivo; toda activación y desactivación guarda **usuario y fecha-hora**, y el **motivo es opcional** en HU15. El bloqueo por asignaciones futuras se decide en HU17.
- **R-STF-16** *(negocio, 24/11/2026)*: gestionan el personal **administrador y encargado de eventos**; el **encargado de compras y almacén no tiene acceso** al módulo, ni de lectura. "Vendedor" designa al encargado de eventos, no a un rol distinto.
- **R-STF-17** *(negocio, 24/11/2026)*: si la función es **"otro"**, la **descripción breve de la función real es obligatoria**; con cualquier otra función, la descripción no se registra.

## 6. Fuera de alcance
- **Disponibilidad, asignación a eventos y cruces de horario** (HU17, RN12): esta historia no crea asignaciones ni valida solapamientos.
- Pagos, planilla o liquidaciones al personal (el pago acordado es parte de la asignación, HU17; los egresos, de `ledger`).
- **Cuentas de usuario** del sistema y accesos de los trabajadores (`identity`).
- Carga masiva o importación desde Excel; adjuntar fotos, contratos laborales o documentos escaneados.
- Historial de cambios campo por campo (si el sistema ya guarda el cambio con usuario y fecha, alcanza para HU15).
- Frontend (otro repositorio).

## 7. No funcionales
- **Auditoría** (RN03): quién y cuándo en cada alta, edición, activación y desactivación; la baja nunca se pierde.
- **Unicidad garantizada**, no solo por validación de la aplicación: dos registros simultáneos con el mismo documento no deben quedar guardados (verificable con prueba de concurrencia).
- **Datos personales**: documento y teléfono se muestran únicamente a administrador y encargado de eventos; el encargado de compras y almacén no recibe estos datos en ninguna respuesta.
- **Errores en español y accionables**: el mensaje de documento duplicado permite identificar al trabajador existente sin exponer datos de más.
- **Fechas** en UTC, con zona `America/Lima` en la presentación; todo importe —tarifa por evento y monto de hora extra— en **céntimos de sol (`PEN`)**, nunca en decimales.
- **Volumen**: el listado exige **paginación** y filtros para responder con fluidez; se espera un plantel de decenas a pocos cientos de trabajadores **[suposición]**.

## 8. Preguntas abiertas
> Resueltas con el negocio el 24/11/2026.
- [x] **Q1 — Tipo de trabajador**: solo dos valores, `fijo` y `eventual`; no se registra la distinción interno/externo.
- [x] **Q2 — Función**: lista fija del sistema (cocinero, mozo, bartender, ayudante, coordinador) más **"otro"**; editable después con auditoría y la asignación conserva la función con la que se trabajó (RN13, HU17).
- [x] **Q3 — Tarifa**: en céntimos de sol (`PEN`), **por evento**, opcional y referencial; la ficha añade si **aplica hora extra** y, solo entonces, un monto referencial por hora extra variable.
- [x] **Q4 — Documento**: se admiten **DNI y carné de extranjería (CE)**, con su tipo; se normaliza quitando espacios y guiones y la unicidad **incluye a los inactivos**.
- [x] **Q5 — Campos obligatorios**: **solo nombre y documento** (tipo + número); teléfono y tarifa opcionales; el teléfono, si se informa, solo dígitos y sin longitud fija.
- [x] **Q6 — Desactivación**: se permite **reactivar**; usuario y fecha-hora siempre; **motivo opcional**; el bloqueo o aviso por asignaciones futuras se decide en HU17.
- [x] **Q7 — Listado**: filtros por **función** y **estado**, búsqueda por **nombre o documento** y **paginación**.
- [x] **Q8 — Permisos**: **administrador y encargado de eventos** gestionan el personal; **encargado de compras y almacén, sin acceso** (ni lectura).
- [x] **Q9 — Alcance de la unicidad del documento**: es por **tipo + número**; un DNI y un CE con el mismo número pueden coexistir, y dos trabajadores no repiten la misma combinación, estén activos o inactivos.
- [x] **Q10 — Descripción de la función "otro"**: cuando la función es "otro" se exige una **descripción breve obligatoria** de la función real; con las demás funciones no se registra descripción.
- [x] **Q11 — Formato del documento**: **DNI de 8 dígitos**; **CE solo dígitos, entre 9 y 12**; se normaliza quitando espacios y guiones.

> **Nota de cierre**: DOMAIN.md §9 ya refleja que el encargado de compras y almacén **no tiene acceso al personal**, ni de lectura (fila «Personal (trabajadores)»). Coherente con §2, CA-15.23, R-STF-16 y Q8.
>
> **Nota de validación**: la respuesta fue "obligatorios: solo nombre y documento", así que **función y tipo** quedan como datos opcionales. Si negocio prefiere exigirlos, debe confirmarlo; aquí no se asume.
