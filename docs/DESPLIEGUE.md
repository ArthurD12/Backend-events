# Despliegue gratuito: Neon + Render + Vercel

Guía para publicar Darze en internet sin costo, para la demostración del proyecto.

| Parte | Servicio | Plan gratuito |
|---|---|---|
| Base de datos (PostgreSQL) | [Neon](https://neon.com) | 1 GB por proyecto; se duerme a los 5 min sin uso. No vence. |
| Backend (esta API) | [Render](https://render.com), servicio web con Docker | 750 horas al mes; se apaga a los 15 min sin tráfico. |
| Frontend (Next.js) | [Vercel](https://vercel.com), plan Hobby | Uso no comercial. |

> **Limitación del plan gratuito**: si nadie usa el sistema por un rato, el primer ingreso tarda
> hasta ~1 minuto (Render y Neon "despiertan"). Antes de una presentación, abre el sistema
> 5 minutos antes.

> **Seguridad**: las claves (`DATABASE_URL`, `JWT_SECRET`) se pegan **solo en los paneles de Neon,
> Render y Vercel**. Nunca en el chat, en un commit ni en el `.env.example`.

Orden: **1. Neon → 2. Render → 3. Vercel → 4. CORS → 5. Administrador.**

---

## 1. Base de datos en Neon

1. Entra a <https://neon.com> e inicia sesión con GitHub.
2. **Create project**:
   - Nombre: `darze`.
   - Postgres version: **17**.
   - Región: **AWS US East (N. Virginia)**, la misma zona que Render (paso 2), para que la API y
     la base estén cerca.
3. En el panel del proyecto, botón **Connect**:
   - Desactiva **Connection pooling** (la API usa conexión directa).
   - Copia la cadena que empieza con `postgresql://…?sslmode=require&channel_binding=require`.
     Se pega **tal cual** en Render: la API la convierte sola al formato que necesita.

Las tablas no se crean a mano: la API aplica las migraciones cada vez que arranca.

## 2. Backend en Render

El repositorio del backend es público, así que Render lo lee sin instalar nada en GitHub.

1. Entra a <https://render.com> e inicia sesión con GitHub.
2. **New → Web Service → Public Git Repository** y pega:
   `https://github.com/ArthurD12/Backend-events`
3. Configuración:
   - **Name**: `darze-api` (la dirección será `https://darze-api.onrender.com` o parecida).
   - **Branch**: `main`.
   - **Region**: **Virginia (US East)**.
   - **Runtime / Language**: **Docker** (usa el `Dockerfile` del repositorio).
   - **Instance type**: **Free**.
   - **Health Check Path** (en *Advanced*): `/health` (no depende de la base: si Neon se
     duerme un momento, Render no reinicia la API).
4. **Environment Variables** (en *Advanced*):

   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | La cadena de Neon del paso 1 |
   | `JWT_SECRET` | Una clave nueva de 48 caracteres o más. Generarla en tu PC: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`. **No reutilices la de tu `.env`**. |
   | `CORS_ORIGINS` | Por ahora `["http://localhost:3000"]`; se cambia en el paso 4 |
   | `COMPANY_NAME` | `Darze Catering` |
   | `COMPANY_RUC`, `COMPANY_ADDRESS`, `COMPANY_PHONE`, `COMPANY_EMAIL` | Los datos reales de Darze, si ya los tienen (los vacíos no se imprimen en el PDF) |

5. **Deploy Web Service**. En *Logs* debe aparecer `Running upgrade … cancelar eventos` y
   `Application startup complete`.
6. Comprueba en el navegador: `https://<tu-servicio>.onrender.com/ready` → `{"status":"ready"}`.

**Actualizar después**: como Render lee el repositorio público sin la app de GitHub, **no se
redespliega solo**. Cada vez que se une algo a `main`: Render → `darze-api` →
**Manual Deploy → Deploy latest commit**.

## 3. Frontend en Vercel

El repositorio del frontend es privado y de otra cuenta, así que se sube **desde tu PC** con la
herramienta de Vercel (no hace falta conectar GitHub).

En la carpeta del frontend, en la rama `main` actualizada:

```bash
npx vercel login
```

```bash
npx vercel link
```

Responde: crear un proyecto nuevo, nombre `darze`, carpeta `./`, sin cambiar la configuración
detectada (Next.js).

Agrega la dirección de la API (se usa al compilar):

```bash
npx vercel env add NEXT_PUBLIC_API_URL production
```

Cuando lo pida, pega `https://<tu-servicio>.onrender.com` (sin `/` al final).

Publica:

```bash
npx vercel --prod
```

Al terminar muestra la dirección, por ejemplo `https://darze.vercel.app`.

**Actualizar después**: repite `npx vercel --prod` desde la rama `main` actualizada.

## 4. Permitir el frontend en la API (CORS)

En Render → `darze-api` → **Environment**, cambia `CORS_ORIGINS` por la dirección de Vercel:

```
["https://darze.vercel.app"]
```

Guarda: Render se reinicia solo. Sin este paso, el inicio de sesión falla con un error de CORS
en la consola del navegador.

## 5. Crear el primer administrador

Render gratuito no tiene consola, así que el administrador se crea **desde tu PC** contra la base
de Neon. En la carpeta del backend (Windows, `cmd`):

```bash
set DATABASE_URL=postgresql://...cadena de Neon...
```

```bash
uv run python -m local_eventos.tools.create_admin
```

Escribe nombre, correo y contraseña. Después cierra esa ventana de `cmd`, para que la variable
no quede definida.

Entra a la dirección de Vercel con ese usuario y crea los demás desde **Usuarios**.

## Problemas comunes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El primer ingreso tarda ~1 minuto | Render o Neon estaban dormidos | Normal en el plan gratuito; espera y recarga |
| "Failed to fetch" o error de CORS al iniciar sesión | `CORS_ORIGINS` no tiene la dirección exacta de Vercel | Paso 4: misma dirección, con `https://` y sin `/` al final |
| El frontend llama a `localhost:8000` | `NEXT_PUBLIC_API_URL` no estaba al compilar | Paso 3: agrega la variable y vuelve a correr `npx vercel --prod` |
| Render falla al arrancar con `JWT_SECRET` | Falta o tiene menos de 32 caracteres | Paso 2, tabla de variables |
| `/ready` responde 503 | La API no llega a la base | Revisa `DATABASE_URL` (sin pooling) en Render |
