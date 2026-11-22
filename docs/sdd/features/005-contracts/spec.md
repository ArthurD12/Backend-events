# Spec: Contrato, firma y adelanto

- **ID**: 005-contracts
- **Estado**: aprobado (César Suclupe, 22/11/2026)
- **Módulos afectados**: `commercial` (submódulo `contracts`), `ledger` (primer registro de pagos), `identity` (permisos)
- **Historias**: HU41 y HU42 (RF102 y RF103). HU43 (PDF del contrato, RF104) queda para después: ver §8.
- **Fuente**: documento del proyecto, tercer avance, épica E03 «Cotizaciones y contratos», aprobado por Darze.

## 1. Problema y objetivo
Una cotización aceptada todavía no compromete a nadie: Darze necesita formalizar el servicio con un contrato y cobrar un adelanto antes de reservar la fecha. Hoy eso se hace en papel, sin relación con la cotización. El objetivo es generar el contrato desde la cotización aceptada, registrar su firma y el adelanto, y poder anularlo con su motivo.

## 2. Actores
- **Encargado de eventos** y **administrador**: generan el contrato, registran la firma y el adelanto, y lo anulan.
- **Encargado de compras y almacén**: no usa contratos.

## 3. Historias
- **HU41**: Como encargado de eventos, quiero generar un contrato a partir de una cotización aceptada, para formalizar el servicio con el cliente.
- **HU42**: Como administrador, quiero registrar la firma del contrato y el adelanto pactado, para confirmar la reserva de la fecha. *(El Product Owner amplió el actor: también el encargado de eventos; ver §5.)*

## 4. Criterios de aceptación (texto del documento)
### HU41
- **CA-41.1**: Solo se genera desde una cotización **aceptada** y **sin contrato previo**.
- **CA-41.2**: Copia los datos de la cotización (cliente, evento, servicios e importe total) **sin permitir modificarlos**.
- **CA-41.3**: El adelanto es del **50 % por defecto** y puede ajustarse.
- **CA-41.4**: La fecha límite del saldo es **siete días antes del evento**.
- **CA-41.5**: El contrato inicia en estado **«pendiente de firma»**.

### HU42
- **CA-42.1**: Registra la **fecha de firma** y el **firmante**.
- **CA-42.2**: Un contrato **firmado no puede editarse**.
- **CA-42.3**: Solo un contrato **firmado y con adelanto pagado** puede convertirse en evento (HU10).
- **CA-42.4**: La **anulación exige un motivo**.
- **CA-42.5** (RF103): el adelanto se almacena en el **módulo de pagos** como el **primer pago** del evento.

## 5. Reglas de negocio
- Código único `CON-AAAA-NNNN`, con correlativo por año (DOMAIN.md §4, reglas 1 y 8).
- Ciclo: `pendiente de firma → firmado | anulado`. Un firmado también se puede anular (con motivo).
- **R-CON-1** *(equipo, 22/11/2026, provisional)*: la firma y el adelanto se registran **en un solo paso**: fecha de firma, firmante y el pago del adelanto (fecha, medio de pago y referencia). El monto del adelanto es el pactado. Así no existe un contrato firmado sin adelanto.
- **R-CON-2** *(equipo, provisional)*: el adelanto pactado es mayor que cero y no supera el total. Si no se indica, es el 50 % del total, redondeado al céntimo.
- **R-CON-3** *(Product Owner, 22/11/2026)*: **cancelación sin reglas automáticas**. Anular registra el motivo y, si hubo devolución, su monto (no mayor que lo pagado) y una nota. El sistema no calcula penalidades.
- **R-CON-4** *(Product Owner, 22/11/2026)*: firma, adelanto y anulación los registran el **administrador y el encargado de eventos** (cambio respecto del texto de HU42).
- **R-CON-5** *(equipo, provisional)*: una cotización tiene **un solo contrato**, aunque se anule. Para volver a contratar se hace una cotización nueva (como DOMAIN.md §4, regla 14).
- Medios de pago: efectivo, transferencia, tarjeta, Yape/Plin (DOMAIN.md §6). Los pagos **no se borran ni se editan** (AGENTS.md, regla 5): la devolución es un movimiento aparte.

## 6. Fuera de alcance
- **HU43**: PDF del contrato.
- **HU10**: convertir el contrato en evento (siguiente historia; este spec deja lista la condición CA-42.3).
- **HU19**: pagos parciales y control del saldo (amplía el registro de pagos que nace aquí).

## 7. No funcionales
- Auditoría: quién generó, firmó o anuló, y cuándo (RN03).
- Concurrencia: dos contratos simultáneos de la misma cotización no pueden existir (lo garantiza la base de datos).
- Pagos de solo inserción, protegidos por trigger, como el historial de accesos.

## 8. Preguntas abiertas
- [x] Cancelación y devolución → sin reglas, solo registro (Harold, 22/11/2026).
- [x] ¿Quién registra pagos, firma y adelanto? → administrador y encargado de eventos (Harold, 22/11/2026).
- [ ] **HU10 contradice a HU42**: el issue #11 dice "solo una cotización aceptada podrá convertirse en evento". HU42, posterior y validada por Darze, exige un contrato firmado con adelanto. Pedir a Harold que actualice el texto de HU10.
- [ ] **HU43 / RF104**: el PDF del contrato debe mostrar "las condiciones y la política de cancelación". Darze no tiene reglas de cancelación: hace falta que defina el **texto de las condiciones** del contrato antes de HU43.
