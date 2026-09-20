# Alertas diarias de Mercado Público — Región del Maule y Ñuble

Revisa cada día las **Licitaciones** nuevas publicadas en Mercado Público que
coincidan con tus palabras clave (cámaras, vigilancia, enlaces, ANPR, CCTV,
televigilancia, redes, telecomunicaciones) y estén en la Región del Maule o
Ñuble, y te envía un correo con el resumen.

⚠️ **Compra Ágil no tiene API pública** (solo Licitaciones, Trato Directo y
Convenio Marco). Este sistema cubre Licitaciones; para Compra Ágil sigue
siendo necesario mantener tus rubros actualizados en tu Escritorio de
Proveedor.

## Paso 1 — Crear el repositorio en GitHub

1. Crea un repositorio **privado** en tu cuenta de GitHub (por ejemplo,
   `alertas-mercadopublico`).
2. Sube todos los archivos de esta carpeta a ese repositorio (mismo árbol de
   carpetas, incluida `.github/workflows/alerta-diaria.yml`).

## Paso 2 — Obtener una "contraseña de aplicación" de Gmail

Para que el script pueda enviar correos desde tu cuenta de Gmail sin exponer
tu contraseña real:

1. Activa la verificación en 2 pasos en tu cuenta de Google (si no la tienes).
2. Ve a https://myaccount.google.com/apppasswords
3. Genera una contraseña de aplicación (elige "Otra" y ponle un nombre, ej.
   "Alertas Mercado Público").
4. Copia la contraseña de 16 caracteres que te entrega — la vas a necesitar
   en el paso siguiente.

Si prefieres usar otro proveedor de correo (Outlook, un dominio propio,
etc.), cambia `SMTP_HOST`/`SMTP_PORT` como variables de entorno en el
workflow (por defecto usa Gmail).

## Paso 3 — Configurar los "Secrets" en GitHub

En tu repositorio: **Settings → Secrets and variables → Actions → New
repository secret**. Crea estos cuatro secrets:

| Nombre               | Valor                                                        |
|----------------------|---------------------------------------------------------------|
| `MP_TICKET`          | Tu ticket de api.mercadopublico.cl                            |
| `EMAIL_FROM`         | La cuenta de Gmail que envía el correo                        |
| `EMAIL_APP_PASSWORD` | La contraseña de aplicación de 16 caracteres del paso 2       |
| `EMAIL_TO`           | El correo que recibe la alerta (puedes poner varios separados por coma) |

Nunca escribas estos valores directamente en el código ni en el repositorio.

## Paso 4 — Probarlo

1. Ve a la pestaña **Actions** de tu repositorio.
2. Selecciona el workflow "Alerta diaria Mercado Público".
3. Haz clic en **Run workflow** (botón "workflow_dispatch") para probarlo
   manualmente sin esperar al cron.
4. Revisa los logs de la ejecución y tu bandeja de entrada.

## Paso 5 — Listo

A partir de ahí corre solo, de lunes a viernes a las 12:00 UTC
(~08:00-09:00 hora de Chile continental, según horario de verano). Es
gratuito: GitHub Actions da 2.000 minutos/mes gratis en repos privados, y
esta tarea usa unos pocos minutos por ejecución.

## Ajustar los filtros

Todo se ajusta directamente en `alerta_mercadopublico.py`:

- `REGIONES_OBJETIVO`: lista de regiones a monitorear (por defecto `maule` y
  `nuble`, sin tildes).
- `PALABRAS_CLAVE`: lista de palabras clave (sin tildes, minúsculas). Agrega
  o quita las que necesites.
- El cron (`.github/workflows/alerta-diaria.yml`) para cambiar el horario o
  los días de ejecución.

## Cómo funciona por dentro

1. Cada día consulta el listado básico de licitaciones **publicadas** ese
   día (`GET licitaciones.json?fecha=...&estado=publicada`).
2. Para cada una, pide el **detalle completo** (región del comprador,
   descripción, ítems solicitados).
3. Se queda solo con las que son de Maule/Ñuble **y** mencionan alguna de
   tus palabras clave (en el título, la descripción o los ítems).
4. Arma una tabla HTML con los resultados y la envía por correo.
