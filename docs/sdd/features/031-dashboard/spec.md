# Spec: Panel de indicadores del administrador (primera parte)

- **ID**: 031-dashboard
- **Estado**: borrador (pendiente de aprobación)
- **Módulos afectados**: `reporting` (nuevo endpoint), `commercial` (consulta de solo lectura vía `public_api`), `identity` (permiso nuevo)
- **Historia**: HU31 (#32), **parcial**: solo los indicadores que ya tienen datos reales

## 1. Problema y objetivo
El administrador no tiene una vista rápida de cómo va el negocio: tiene que entrar a cotizaciones y contar a mano. El objetivo es que, al iniciar sesión, vea un resumen con datos **reales**. Los indicadores de módulos que todavía no existen (caja, stock) no se muestran, ni siquiera en cero: se agregan cuando esos módulos estén listos.

## 2. Actores
- **Administrador**: ve el panel.
- **Encargado de eventos** y **encargado de compras y almacén**: su Inicio se mantiene como hoy, con las tarjetas de sus módulos. No acceden al panel, ni desde la pantalla ni desde la API.

## 3. Historia
- **HU31**: Como administrador, quiero visualizar indicadores generales en un dashboard, para conocer rápidamente la situación operativa de Darze.

## 4. Criterios de aceptación
- **CA-31.1**: El panel muestra cuántas cotizaciones hay **en borrador** y cuántas **enviadas esperando respuesta** (sin contar las vencidas).
- **CA-31.2**: Para el **mes elegido** (por defecto, el actual en hora de Lima) muestra cuántas cotizaciones se **crearon**, cuántas se **aceptaron** y el **monto aceptado** en soles.
- **CA-31.3**: Muestra las **próximas fechas**: cotizaciones aceptadas con evento en los próximos 30 días, de la más cercana a la más lejana, con el aviso de que el contrato todavía no se registra en el sistema.
- **CA-31.4**: Muestra las **5 cotizaciones más recientes**, con acceso a cada una.
- **CA-31.5**: Solo el administrador ve el panel. Para los demás roles, la API responde 403.
- **CA-31.6**: El mes se cambia con un selector, y los indicadores del mes se actualizan.

## 5. Reglas
- Ningún número se inventa ni se rellena: si no hay datos, se muestra 0 o una lista vacía con su explicación.
- "Aceptadas en el mes" cuenta las cotizaciones **creadas** en ese mes que hoy están aceptadas. El sistema todavía no guarda la fecha en que se aceptó cada una (ver §8).

## 6. Fuera de alcance (llega con sus módulos)
- Caja actual (HU19–HU22), alertas de stock bajo (HU23) y eventos reales (HU10/HU41).
- Gráficos históricos de varios meses.

## 7. No funcionales
- Una sola petición al backend para todo el panel (lo pide la tarea de HU31).
- Sin tablas nuevas ni servicios nuevos: se calcula al consultar.

## 8. Preguntas abiertas
- [x] ¿Solo para el administrador? → Sí (César, 22/11/2026).
- [ ] Más adelante: guardar la fecha de aceptación de cada cotización, para medir "aceptadas en el mes" por la fecha real de aceptación. Se decide con HU41 (contrato).
