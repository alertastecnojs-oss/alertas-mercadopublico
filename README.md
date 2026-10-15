# Alertas diarias de Mercado Público — Región del Maule y Ñuble

Revisa cada día las oportunidades nuevas de Mercado Público que coincidan
con tus palabras clave (cámaras, vigilancia, enlaces, ANPR, CCTV,
televigilancia, redes, telecomunicaciones) y estén en la Región del Maule
o Ñuble, y te envía un correo con el resumen. Cubre dos mecanismos, **ambos
vía API oficial**:

1. **Licitaciones** — `api.mercadopublico.cl` (API clásica, v1).
2. **Compra Ágil** — `api2.mercadopublico.cl` (API nueva, v2, lanzada por
   ChileCompra en mayo de 2026). Hasta esa fecha Compra Ágil no tenía API
   pública; ahora sí, y es la que usa este script — nada de navegador ni
   scraping.

## Paso 1 — Crear el repositorio en GitHub

1. Crea un repositorio **privado** en tu cuenta de GitHub (por ejemplo,
   `alertas-mercadopublico`).
2. Sube todos los archivos de esta carpeta a ese repositorio (mismo árbol de
   carpetas, incluida `.github/workflows/alerta-diaria.yml`).

## Paso 2 — Obtener una "contraseña de aplicación" de Gmail

1. Activa la verificación en 2 pasos en tu cuenta de Google (si no la tienes).
2. Ve a https://myaccount.google.com/apppasswords
3. Genera una contraseña de aplicación (elige "Otra" y ponle un nombre, ej.
   "Alertas Mercado Público").
4. Copia la contraseña de 16 caracteres que te entrega.

## Paso 3 — Configurar los "Secrets" en GitHub

**Settings → Secrets and variables → Actions → New repository secret**:

| Nombre               | Valor                                                        |
|----------------------|---------------------------------------------------------------|
| `MP_TICKET`          | Tu ticket de api.mercadopublico.cl                            |
| `EMAIL_FROM`         | La cuenta de Gmail que envía el correo                        |
| `EMAIL_APP_PASSWORD` | La contraseña de aplicación de 16 caracteres del paso 2       |
| `EMAIL_TO`           | El correo que recibe la alerta (puedes poner varios separados por coma) |

**Nota sobre el ticket de Compra Ágil**: el script usa el mismo `MP_TICKET`
para ambas APIs (v1 y v2), porque el ticket se obtiene en el mismo lugar
(https://www.chilecompra.cl/api/ → "Pide tu ticket"). Si al correrlo la
parte de Compra Ágil falla con error 401/403, es porque tu ticket actual
no tiene permiso en la API nueva — pide uno nuevo en ese mismo portal y
agrega un secret adicional `MP_TICKET_COMPRA_AGIL` con ese valor (el
script lo usa automáticamente si existe; si no, sigue usando `MP_TICKET`).

## Paso 4 — Probarlo

1. Pestaña **Actions** → workflow "Alerta diaria Mercado Público" → **Run
   workflow**.
2. Revisa el log: primero la sección de Licitaciones, luego "=== Compra
   Ágil (API oficial) ===" buscando cada palabra clave.
3. Revisa tu bandeja de entrada (y spam) — el correo trae dos tablas, una
   por cada mecanismo.

## Ajustar los filtros

Todo se ajusta en **un solo lugar**: `common.py`.

- `PALABRAS_CLAVE`: lista de palabras clave (sin tildes, minúsculas). Ojo:
  el script de Compra Ágil hace **una consulta a la API por cada palabra
  clave** (para aprovechar la búsqueda propia de la API sobre nombre y
  descripción), así que agregar muchas palabras hace la corrida un poco
  más lenta — no es un problema para una lista de ~10-15 palabras.
- `REGIONES_OBJETIVO`: diccionario `{nombre: código_región}`. Ya trae Maule
  (7) y Ñuble (16), según la tabla oficial de códigos de región (1 a 16)
  que usa Mercado Público en todas sus APIs.

El horario y los días de ejecución se ajustan en
`.github/workflows/alerta-diaria.yml` (cron, en UTC).

## Desactivar temporalmente Compra Ágil

Si por algún motivo quieres que el correo solo traiga Licitaciones,
agrega el secret `INCLUIR_COMPRA_AGIL` con valor `0` y pásalo también como
variable de entorno en el workflow (`env:` del paso "Ejecutar script de
alertas"). El script se salta por completo esa sección; si falla igual
(cuota agotada, ticket sin permiso, etc.) tampoco corta el correo — solo
agrega un aviso y sigue con las Licitaciones.

## Límites y cuota de las APIs

- **Licitaciones (v1)**: 10.000 solicitudes diarias por ticket. El script
  hace 1 + (una por cada licitación publicada ese día) — normalmente muy
  por debajo del límite.
- **Compra Ágil (v2)**: cuota diaria por ticket (el valor exacto depende
  del tipo de ticket asignado). El script hace 1 solicitud por palabra
  clave (más una extra por cada página adicional de resultados) — con
  ~10-15 palabras clave, unas 10-30 solicitudes diarias, muy por debajo de
  cualquier límite razonable.
- Si alguna vez ves un error 429 en el log, la cuota de esa API se agotó
  por ese día — no es un bug, solo espera al día siguiente (se resetea a
  medianoche UTC).

## Cómo funciona por dentro

**Licitaciones** (`alerta_mercadopublico.py`):
1. Consulta el listado básico de licitaciones **publicadas** ese día.
2. Para cada una, pide el **detalle completo** (región, descripción, ítems).
3. Filtra por región + palabra clave (título, descripción o ítems).

**Compra Ágil** (`alerta_compra_agil.py`):
1. Para cada palabra clave, consulta `GET /v2/compra-agil` filtrando por
   región (Maule + Ñuble en una sola llamada), estado `publicada`, y fecha
   de publicación = hoy.
2. Pagina automáticamente si hay más de 50 resultados.
3. Verifica localmente la coincidencia de palabra clave en el nombre (por
   si el buscador de la API es más amplio de lo esperado) y elimina
   duplicados entre distintas palabras clave.

Ambos resultados se combinan en un único correo HTML. Si Compra Ágil falla
por cualquier motivo, el correo se envía igual con un aviso — nunca te
quedas sin correo por un problema en esa parte.

## Memoria entre ejecuciones

El programa recuerda lo que ya vio, en el archivo `vistos_mercadopublico.json`
(código en `estado.py`):

- **Licitaciones ya revisadas:** no se vuelve a consultar su detalle, lo que
  acorta mucho la ejecución (solo se revisan las nuevas).
- **Avisos ya enviados:** una licitación o Compra Ágil aparece en el correo
  una sola vez, aunque siga abierta varios días.

En GitHub el archivo se conserva con `actions/cache` (no se sube al
repositorio). Si la caché expira (GitHub la borra tras 7 días sin uso) o se
borra a mano, el programa parte de cero: funciona igual, pero esa vez puede
avisar de cosas que ya habías visto. Se olvidan los códigos tras 60 días.
