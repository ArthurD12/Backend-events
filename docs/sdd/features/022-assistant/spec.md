# Spec: Asistente de consulta con IA

- **ID**: 022-assistant
- **Estado**: borrador
- **Módulos afectados**: `assistant` (nuevo contenido), lectura por `public_api` de `commercial`, `ledger`, `inventory`, `purchasing`, `reporting`, `staff` (si publica consultas), `identity`
- **Historias**: HU35–HU37 (#34), HU38–HU39 (#35), HU40 (#36)

## 1. Problema y objetivo
Para saber "¿cuánto le falta pagar al cliente X?" o "¿qué eventos tengo esta semana?" hay que navegar varias pantallas. El objetivo es un **chat de consulta** dentro del sistema que responde en lenguaje natural **con datos reales**, respetando el rol del usuario y sin inventar.

## 2. Actores
- Los tres roles usan el asistente; cada uno solo consulta lo que su rol permite (RN27, RN28).
- **Administrador**: ve el historial de consultas de todos (HU40).

## 3. Historias
- **HU35–HU37**: hacer preguntas en lenguaje natural y recibir respuestas con datos del sistema.
- **HU38–HU39**: el asistente respeta permisos, pide aclaración si la pregunta es ambigua y no inventa.
- **HU40**: cada consulta queda registrada para auditoría.

## 4. Criterios de aceptación
- **CA-35.1**: Un chat en el sistema (botón flotante o menú "Asistente") donde el usuario escribe una pregunta y recibe la respuesta en segundos.
- **CA-35.2**: Responde usando solo **funciones de consulta controladas** (RN29), por ejemplo:
  1. Próximos eventos (rango de fechas).
  2. Detalle de un evento por código (estado, fecha, lugar, invitados, responsable).
  3. Cuenta de un evento o contrato: total, pagado, saldo, vencimiento.
  4. Cobros pendientes y vencidos.
  5. Stock de un producto / productos con stock bajo o por vencer.
  6. Requerimiento y faltantes de un evento.
  7. Compras abiertas.
  8. Flujo de caja de un mes (solo con `finance:read`).
  9. Buscar cliente por nombre y su historial resumido.
  10. Personal asignado a un evento (cuando el módulo de personal lo publique).
- **CA-35.3**: Mantiene el hilo de la conversación en la sesión de chat (preguntas de seguimiento como "¿y su saldo?").
- **CA-38.1**: **Solo consulta** (RN30): ninguna función registra, cambia, aprueba, anula ni elimina.
- **CA-38.2**: Cada función verifica el **permiso del usuario** antes de devolver datos (RN28); si no tiene permiso, el asistente lo dice.
- **CA-39.1**: Si la pregunta es ambigua (p. ej. dos clientes con el mismo nombre), **pide aclaración** (RN31).
- **CA-39.2**: Si no hay datos o la pregunta está fuera de lo que puede consultar, **lo dice y no inventa** (RN32). Los montos y fechas de la respuesta salen tal cual de las funciones.
- **CA-40.1**: Cada consulta guarda usuario, fecha, pregunta, funciones ejecutadas (con sus parámetros) y respuesta (RN33). El administrador ve el historial con filtros.
- **CA-40.2**: Sin clave del proveedor configurada, el asistente aparece "no disponible" y el resto del sistema funciona igual.

## 5. Reglas
- **R-IA-1** *(equipo, provisional)*: proveedor **Anthropic (Claude)**, modelo `claude-opus-5-5`, detrás del puerto `LanguageModel` (cambiarlo no toca el dominio). El documento del proyecto mencionaba OpenAI; se decide en ADR 0005.
- **R-IA-2** *(equipo, provisional)*: límite de **30 preguntas por usuario por hora** y respuestas cortas, para acotar costo (el sistema queda en portafolio público).
- **R-IA-3** *(equipo, provisional)*: la conversación vive en la sesión del chat (no se guarda el historial completo como contexto entre días); el registro de auditoría sí se guarda.
- **R-IA-4** *(equipo, provisional)*: respuestas en español, montos en soles y fechas en hora de Lima.

## 6. Fuera de alcance
- Acciones (crear, editar, pagar) desde el chat.
- Voz, archivos o imágenes.
- Respuestas sobre información que no está en el sistema.
