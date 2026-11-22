# Spec: Inicio de sesión, usuarios e historial de accesos

- **ID**: 001-identity
- **Estado**: aprobado (César Suclupe, 22/11/2026)
- **Módulos afectados**: `identity` (nuevo contenido); `commercial` y `catalog` (rutas protegidas)
- **Historias**: HU01 (#2), HU02 (#3), HU03 (#4)

## 1. Problema y objetivo
Hoy cualquiera que llegue a la API puede ver y modificar clientes y catálogo. Darze necesita que solo su personal entre al sistema, cada uno con su cuenta, y que cada persona vea y haga únicamente lo que corresponde a su rol. El administrador además necesita saber quién entró, cuándo, y quién intentó entrar sin éxito.

## 2. Usuarios / actores
- **Administrador**: crea y administra las cuentas del personal y revisa el historial de accesos.
- **Encargado de eventos** y **encargado de compras y almacén**: inician y cierran sesión y usan solo sus módulos.
- **Persona no autorizada**: no debe poder entrar ni usar la API.

## 3. Historias de usuario
- **HU01**: Como usuario autorizado, quiero iniciar y cerrar sesión para acceder de manera segura a las funciones de mi rol.
- **HU02**: Como administrador, quiero registrar, modificar, activar y desactivar usuarios para controlar quiénes usan el sistema.
- **HU03**: Como administrador, quiero consultar el historial de accesos para identificar intentos fallidos y verificar el uso de las cuentas.

## 4. Criterios de aceptación
### HU01: iniciar y cerrar sesión
- **CA-01.1**: Dado un usuario activo, cuando ingresa su correo y contraseña correctos, entonces entra al sistema.
- **CA-01.2**: Dado un correo inexistente o una contraseña incorrecta, cuando intenta entrar, entonces ve "acceso rechazado". El mensaje no revela cuál de los dos falló.
- **CA-01.3**: Dado un usuario desactivado, cuando intenta entrar con su contraseña correcta, entonces no entra.
- **CA-01.4**: Dado un usuario que entró, cuando el sistema le informa su perfil, entonces recibe su rol y su lista de permisos, para que la pantalla muestre solo los módulos permitidos.
- **CA-01.5**: Dado un usuario que entró, cuando cierra sesión, entonces su sesión ya no se puede renovar.
- **CA-01.6**: Dado un usuario sin actividad durante 30 minutos, cuando vuelve a usar el sistema, entonces debe iniciar sesión otra vez.
- **CA-01.7**: Dada una ruta protegida, cuando se llama sin sesión, responde 401; cuando el rol no tiene el permiso, responde 403.

### HU02: gestión de usuarios
- **CA-02.1**: El administrador crea un usuario con nombre, correo, contraseña, rol y estado.
- **CA-02.2**: El correo no puede repetirse en otra cuenta, sin importar mayúsculas.
- **CA-02.3**: El administrador modifica nombre, correo y rol de un usuario y, si hace falta, le asigna una contraseña nueva.
- **CA-02.4**: Un usuario desactivado no puede iniciar sesión, y sus sesiones abiertas dejan de renovarse.
- **CA-02.5**: Desactivar no elimina al usuario ni su historial.
- **CA-02.6**: Solo el administrador gestiona usuarios.

### HU03: historial de accesos
- **CA-03.1**: Cada intento de inicio de sesión registra el correo ingresado, el usuario (si existe), la fecha y hora, y el resultado.
- **CA-03.2**: Solo el administrador consulta el historial.
- **CA-03.3**: El historial se filtra por usuario, rango de fechas y resultado, y se pagina.
- **CA-03.4**: Nadie puede modificar ni borrar registros del historial, ni siquiera desde la base de datos con el usuario de la aplicación.

## 5. Reglas de negocio
- **RN01**: Cada persona tiene su propia cuenta. El correo identifica la cuenta.
- **RN02**: Los usuarios no se eliminan, se desactivan.
- **R-ID-1** *(provisional, decidido por el equipo el 22/11/2026)*: la contraseña tiene **mínimo 8 caracteres**, sin exigir símbolos.
- **R-ID-2** *(provisional, 22/11/2026)*: los intentos fallidos **solo se registran** en el historial; la cuenta no se bloquea.
- **R-ID-3**: los permisos de cada rol siguen la tabla de `DOMAIN.md` §9. Los roles son fijos: administrador, encargado de eventos, encargado de compras y almacén.
- **R-ID-4**: no se puede desactivar ni quitar el rol al último administrador activo, para que el sistema no quede sin nadie que lo administre.

## 6. Fuera de alcance
- Recuperar la contraseña por correo ("¿Olvidaste tu contraseña?"): el sistema no envía correos.
- Que cada usuario cambie su propia contraseña: por ahora la asigna el administrador.
- Bloqueo de cuentas por intentos fallidos (R-ID-2).
- Crear roles nuevos o editar los permisos de un rol desde la pantalla.
- Las pantallas del frontend (van en el repositorio del frontend).

## 7. Requisitos no funcionales
- **Seguridad**: las contraseñas se guardan con Argon2 (cifrado de un solo sentido), nunca en texto. Las sesiones se pueden revocar (ADR 0001).
- **Auditoría**: el historial de accesos es de solo inserción.
- **Mantenimiento mínimo**: sin servicios nuevos (sin Redis). Las dos librerías nuevas, `pyjwt` y `pwdlib[argon2]`, ya están decididas en ADR 0001 y listadas en `STACK.md`.
- **Instalación**: un comando crea el primer administrador al instalar el sistema.

## 8. Preguntas abiertas
- [x] Largo mínimo de la contraseña → 8 caracteres (César, 22/11/2026).
- [x] ¿Bloquear tras intentos fallidos? → No, solo registrar (César, 22/11/2026).
- [x] ¿Proteger ya clientes y catálogo? → Sí, en esta feature (César, 22/11/2026).
- [ ] Informar al Product Owner (Harold) las reglas provisionales R-ID-1 y R-ID-2.
