# Spec: Proyecto ejecutable (bootstrap)

- **ID**: 000-bootstrap
- **Estado**: aprobado
- **Módulos afectados**: ninguno de negocio (base del proyecto: `shared/`, configuración, CI)

## 1. Problema y objetivo
El repositorio tiene la estructura de carpetas, pero la aplicación todavía no arranca: no hay dependencias declaradas, base de datos local ni comprobaciones automáticas. Sin esa base, cada integrante configuraría su entorno a su manera y las historias del Sprint 1 (HU01–HU03) no podrían integrarse.

Objetivo: que cualquier integrante, con un clon nuevo del repositorio, pueda levantar la API y la base de datos con pocos comandos, y que cada cambio subido a GitHub se verifique automáticamente.

## 2. Usuarios / actores
- Desarrollador del equipo (César, Harold): necesita levantar el proyecto en su computadora de forma idéntica al otro integrante.
- Revisor del pull request: necesita saber, sin ejecutar nada, si el cambio rompe las pruebas o las reglas de arquitectura.
- Operador futuro (entrega a Darze): necesita saber si la API está viva y si tiene conexión con la base de datos.

## 3. Historias de usuario
- Como desarrollador, quiero levantar la base de datos y la API con pocos comandos documentados, para empezar a programar sin configurar todo a mano.
- Como revisor, quiero que GitHub ejecute las comprobaciones en cada pull request, para no aprobar cambios que rompen el proyecto.
- Como operador, quiero consultar el estado de la API y de su base de datos, para detectar fallas rápidamente.

## 4. Criterios de aceptación
- **CA-1**: Dado un clon nuevo y las herramientas de `docs/INSTALACION.md` instaladas, cuando el desarrollador sigue los pasos de instalación, entonces la base de datos local y la API quedan en ejecución sin pasos adicionales no documentados.
- **CA-2**: Dada la API en ejecución, cuando se consulta el estado de salud, entonces responde que está viva aunque la base de datos no esté disponible.
- **CA-3**: Dada la API en ejecución con la base de datos disponible, cuando se consulta si está lista, entonces responde que sí.
- **CA-4**: Dada la API en ejecución sin base de datos disponible, cuando se consulta si está lista, entonces responde que no está lista, sin exponer detalles internos del error.
- **CA-5**: Dado el proyecto recién configurado, cuando se ejecuta la comprobación completa (`just check`), entonces termina sin errores.
- **CA-6**: Dado un pull request hacia `main`, cuando se sube, entonces GitHub ejecuta la comprobación completa y muestra si pasó o falló.
- **CA-7**: Dado un código que importa una capa prohibida (por ejemplo, el dominio importando el framework web), cuando se ejecuta la comprobación de arquitectura, entonces falla indicando la regla incumplida.
- **CA-8**: Dada la API en ejecución, cuando se solicita la documentación de la API, entonces se obtiene el contrato OpenAPI con la versión `/v1`.
- **CA-9**: Dado el repositorio, cuando se revisan sus archivos, entonces no contiene contraseñas ni claves reales: la configuración sensible se toma de variables de entorno, con un archivo de ejemplo sin secretos.

## 5. Reglas de negocio
- No aplica: esta feature no implementa reglas de Darze. Prepara la base para las historias HU01 en adelante.

## 6. Fuera de alcance
- Usuarios, inicio de sesión, roles y permisos (feature `001-identity`, HU01–HU03).
- Tablas de negocio y migraciones con datos.
- Despliegue en un servidor, copias de seguridad y monitoreo en producción.
- El frontend (vive en otro repositorio).

## 7. Requisitos no funcionales
- **Reproducibilidad:** las versiones de las dependencias quedan fijadas en un archivo de bloqueo versionado.
- **Seguridad:** ningún secreto en el repositorio; el estado de salud no expone información interna.
- **Mantenimiento mínimo:** solo las herramientas ya definidas en `STACK.md`; nada nuevo sin ADR.
- **Compatibilidad:** los pasos de instalación funcionan en Windows (equipo de desarrollo) y en Linux (GitHub Actions).

## 8. Preguntas abiertas
- [x] ¿Ambos integrantes tienen Docker Desktop en Windows? → Sí en el equipo de César (Docker 29.9.2, Compose v5.6.1). Harold lo verifica con `docker compose version` antes de la Sprint Review.
- [x] ¿Python 3.12 o `uv`? → Se usa `uv` (0.13.7) para crear el entorno e instalar dependencias, con Python 3.12. `just` (1.59.0) para los atajos. En Windows se instalan con `winget install --id=astral-sh.uv -e` y `winget install --id=Casey.Just -e`.