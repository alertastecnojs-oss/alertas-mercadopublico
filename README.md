# Alertas diarias de Mercado Público — Región del Maule y Ñuble

Revisa cada día las oportunidades nuevas de Mercado Público que coincidan
con tus palabras clave (cámaras, vigilancia, enlaces, ANPR, CCTV,
televigilancia, redes, telecomunicaciones) y estén en la Región del Maule
o Ñuble, y te envía un correo con el resumen. Cubre dos mecanismos:

1. **Licitaciones** — vía la API oficial `api.mercadopublico.cl`. Robusto,
   con contrato estable.
2. **Compra Ágil** — vía un navegador real (Playwright) contra el buscador
   público `buscador.mercadopublico.cl/compra-agil`, porque **este
   mecanismo no tiene API pública** (confirmado: ni la API clásica ni la
   API OCDS de ChileCompra lo exponen).

## ⚠️ Antes de usarlo, entiende la diferencia entre ambas partes

| | Licitaciones (API) | Compra Ágil (navegador) |
|---|---|---|
| Fuente | API oficial documentada | Buscador web público, sin API |
| Estabilidad | Alta — contrato estable | Media/baja — depende del HTML actual del sitio |
| Qué pasa si ChileCompra cambia algo | No afecta | Puede romperse hasta que se actualice el script |
| Qué pasa si falla | Error visible | **No corta el correo**: se envía igual, con un aviso de que Compra Ágil falló ese día |

Si el sitio de Mercado Público rediseña esa página del buscador, la parte
de Compra Ágil puede dejar de funcionar (dará 0 resultados o un error) sin
que sea un problema con tu configuración — revisa los logs de Actions de
vez en cuando para notarlo a tiempo.

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

## Paso 4 — Probarlo

1. Pestaña **Actions** → workflow "Alerta diaria Mercado Público" → **Run
   workflow**.
2. Revisa el log: debería mostrar primero la sección de Licitaciones y
   luego "=== Compra Ágil (Playwright) ===" con el detalle de cada región
   revisada.
3. Revisa tu bandeja de entrada (y spam) — el correo trae dos tablas, una
   por mecanismo.

## Ajustar los filtros

Ahora todo se ajusta en **un solo lugar**: `common.py`.

- `PALABRAS_CLAVE`: lista de palabras clave (sin tildes, minúsculas).
- `REGIONES_OBJETIVO`: diccionario `{nombre: código_región}`. Ya trae Maule
  (7) y Ñuble (16). Si agregas otra región, necesitas su código numérico
  oficial (lo puedes ver seleccionándola en el buscador de Compra Ágil y
  mirando el parámetro `region=` en la URL).

El horario y los días de ejecución se ajustan en
`.github/workflows/alerta-diaria.yml` (cron, en UTC).

## Desactivar temporalmente Compra Ágil

Si el scraper de Compra Ágil empieza a fallar seguido (por un cambio en el
sitio) y quieres seguir recibiendo solo Licitaciones mientras se arregla,
agrega un quinto secret:

| Nombre | Valor |
|---|---|
| `INCLUIR_COMPRA_AGIL` | `0` |

y pásalo también como variable de entorno en el workflow (`env:` del paso
"Ejecutar script de alertas"). Con `0` el script se salta por completo el
paso de Playwright.

## Cómo funciona por dentro

**Licitaciones:**
1. Consulta el listado básico de licitaciones **publicadas** ese día.
2. Para cada una, pide el **detalle completo** (región, descripción, ítems).
3. Filtra por región + palabra clave (título, descripción o ítems).

**Compra Ágil:**
1. Abre un Chromium headless con Playwright.
2. Para cada región objetivo, navega
   `buscador.mercadopublico.cl/compra-agil` filtrando por esa región y la
   fecha de hoy, paginando resultados.
3. Extrae cada tarjeta de resultado (código, nombre, organismo,
   presupuesto, fecha de cierre) leyendo el texto visible de la página.
4. Filtra por palabra clave en el nombre del proceso.

Ambos resultados se combinan en un único correo HTML.
