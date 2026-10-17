#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alerta diaria de Mercado Público (Chile) — Licitaciones + Compra Ágil
=======================================================================

1. Licitaciones: consulta la API pública de Mercado Público
   (api.mercadopublico.cl), filtra las publicadas el día de ejecución por
   región del comprador y palabras clave, usando el detalle completo de
   cada una (más preciso).

2. Compra Ágil: vía la API oficial api2.mercadopublico.cl (lanzada por
   ChileCompra en mayo de 2026) — ver alerta_compra_agil.py para el detalle.

Ambos resultados se combinan en un solo correo.

Configuración: todo se lee desde variables de entorno (ver README.md /
el workflow de GitHub Actions), nunca se hardcodean credenciales aquí.
Las palabras clave y regiones se editan en common.py (compartido por
ambos scripts).
"""

import os
import sys
import time
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from zoneinfo import ZoneInfo

from common import contiene_palabra_clave, region_coincide
import estado as memoria

# ---------------------------------------------------------------------------
# Configuración (desde variables de entorno)
# ---------------------------------------------------------------------------

MP_TICKET = os.environ["MP_TICKET"]  # Ticket de api.mercadopublico.cl

EMAIL_FROM = os.environ["EMAIL_FROM"]           # cuenta que envía (ej: Gmail)
EMAIL_APP_PASSWORD = os.environ["EMAIL_APP_PASSWORD"]  # contraseña de aplicación
EMAIL_TO = os.environ["EMAIL_TO"]               # destinatario(s), separados por coma
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

# Si CORREO_INCLUYE_COMPRA_AGIL=0, se omite el paso de Playwright (por si
# falla o se quiere desactivar temporalmente sin tocar el workflow).
INCLUIR_COMPRA_AGIL = os.environ.get("INCLUIR_COMPRA_AGIL", "1") != "0"

API_BASE = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
TIMEOUT = 20
PAUSA_ENTRE_LLAMADAS = 0.6  # segundos, para no saturar la API
PAUSA_REINTENTO = 5  # segundos (se multiplica por el número de intento)

# Presupuesto de tiempo para revisar el detalle de las licitaciones (se
# consulta una por una, y son cientos por día en todo el país). Si se
# supera, se corta, se envía el correo igual con lo encontrado y se avisa
# que quedó incompleto. Así nunca se pierde el correo por el timeout de
# 25 min del workflow.
LIMITE_SEG_LICITACIONES = int(os.environ.get("LIMITE_SEG_LICITACIONES", str(14 * 60)))
AVISOS_LICITACIONES = []

# URL pública para ver el detalle de una licitación en el portal
URL_DETALLE = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={codigo}"


def _sin_ticket(valor):
    """Texto del error sin el ticket. Los errores de requests incluyen la URL
    completa (con ?ticket=...), y eso terminaba escrito en el correo y en los
    logs."""
    texto = str(valor)
    for t in {MP_TICKET, os.environ.get("MP_TICKET_COMPRA_AGIL", "")}:
        if t:
            texto = texto.replace(t, "***")
    return texto


class LimiteExcedido(Exception):
    """La API respondió 429 (Too Many Requests)."""


ESPERAS_429_LISTADO = (30, 90, 180)  # segundos entre reintentos del listado
ESPERA_429_DETALLE = 30
MAX_429_SEGUIDOS = 3  # tras tantos 429 seguidos en detalle se corta la revisión


def _get(params):
    """GET a la API de Licitaciones. Si la API responde 429 (límite de
    tasa) u otro error, se propaga la excepción y quien llama decide qué
    hacer — no hay reintentos: se prefiere saltar esa licitación y seguir
    con las demás antes que alargar la corrida esperando."""
    resp = requests.get(API_BASE, params=params, timeout=TIMEOUT)
    if resp.status_code == 429:
        raise LimiteExcedido("HTTP 429 Too Many Requests (límite de uso de la API de Licitaciones)")
    resp.raise_for_status()
    return resp.json()


def obtener_licitaciones_del_dia(fecha_ddmmaaaa):
    """Trae el listado básico de licitaciones publicadas en la fecha dada."""
    params = {"fecha": fecha_ddmmaaaa, "estado": "publicada", "ticket": MP_TICKET}
    # La API a veces responde 500 o se cae un instante: se reintenta (3 veces
    # en total). Un error 4xx (ticket, cuota) no se reintenta.
    ultimo_error = None
    espera_429 = 0
    fallos_5xx = 0
    while True:
        try:
            data = _get(params)
            return data.get("Listado", []) or []
        except LimiteExcedido as e:
            # 429: se espera más tiempo y se reintenta (hasta 3 veces).
            if espera_429 >= len(ESPERAS_429_LISTADO):
                raise
            espera = ESPERAS_429_LISTADO[espera_429]
            espera_429 += 1
            print(f"  429 en el listado del {fecha_ddmmaaaa}; esperando {espera}s", file=sys.stderr)
            time.sleep(espera)
            ultimo_error = e
            continue
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code < 500:
                raise
            ultimo_error = e
        except (requests.ConnectionError, requests.Timeout) as e:
            ultimo_error = e
        fallos_5xx += 1
        if fallos_5xx >= 3:
            raise ultimo_error
        print(f"  reintentando el listado del {fecha_ddmmaaaa} ({_sin_ticket(ultimo_error)})", file=sys.stderr)
        time.sleep(PAUSA_REINTENTO * fallos_5xx)


def obtener_detalle(codigo):
    """Trae el detalle completo de una licitación (región, ítems, etc.)."""
    params = {"codigo": codigo, "ticket": MP_TICKET}
    data = _get(params)
    listado = data.get("Listado", []) or []
    return listado[0] if listado else None



def evaluar_licitacion(detalle):
    """Devuelve un dict con los datos resumidos si la licitación matchea, o None."""
    comprador = detalle.get("Comprador") or {}
    region = comprador.get("RegionUnidad", "") or ""

    if not region_coincide(region):
        return None

    nombre = detalle.get("Nombre", "") or ""
    descripcion = detalle.get("Descripcion", "") or ""

    items = (detalle.get("Items") or {}).get("Listado", []) or []
    texto_items = " ".join(
        f"{it.get('Categoria', '')} {it.get('NombreProducto', '')} {it.get('Descripcion', '')}"
        for it in items
    )

    if not contiene_palabra_clave(nombre, descripcion, texto_items):
        return None

    fechas = detalle.get("Fechas") or {}
    return {
        "codigo": detalle.get("CodigoExterno", ""),
        "nombre": nombre,
        "organismo": comprador.get("NombreOrganismo", ""),
        "comuna": comprador.get("ComunaUnidad", ""),
        "region": region,
        "fecha_cierre": fechas.get("FechaCierre", "") or detalle.get("FechaCierre", ""),
        "tipo": detalle.get("Tipo", ""),
        "url": URL_DETALLE.format(codigo=detalle.get("CodigoExterno", "")),
    }


def obtener_licitaciones(fechas_ddmmaaaa, registro=None):
    """fechas_ddmmaaaa: lista de fechas (típicamente [hoy, ayer]) — se
    consultan todas y se combinan sin duplicados. Esto evita perder
    licitaciones publicadas ayer después de la hora en que corrió el
    script (la API v1 solo permite filtrar por un día exacto, no por
    rango de horas).

    registro: la memoria entre ejecuciones (estado.py). Si se entrega, las
    licitaciones cuyo detalle ya se revisó antes se saltan sin consultar la
    API, y las que se revisan ahora quedan anotadas. Si se agota el tiempo,
    las que faltan NO se anotan, así que se revisan en la próxima ejecución."""
    previas = (registro or {}).get("revisadas", {})
    resultados = {}
    seguidos_429 = 0
    en_corrida = set()
    saltadas = 0
    revisadas_ahora = 0
    inicio = time.monotonic()
    AVISOS_LICITACIONES.clear()

    for fecha in fechas_ddmmaaaa:
        try:
            listado_basico = obtener_licitaciones_del_dia(fecha)
        except (requests.RequestException, LimiteExcedido) as e:
            # Si falla el listado de un día, igual se revisa el otro.
            AVISOS_LICITACIONES.append(f"No se pudo obtener el listado del {fecha[:2]}-{fecha[2:4]}: {_sin_ticket(e)}")
            print(f"AVISO: {AVISOS_LICITACIONES[-1]}", file=sys.stderr)
            continue
        print(f"{len(listado_basico)} licitaciones publicadas el {fecha}.")

        for item in listado_basico:
            codigo = item.get("CodigoExterno")
            if not codigo or codigo in en_corrida:
                continue
            en_corrida.add(codigo)
            if codigo in previas:
                saltadas += 1
                continue
            if time.monotonic() - inicio > LIMITE_SEG_LICITACIONES:
                AVISOS_LICITACIONES.append(
                    f"Licitaciones incompleta: se alcanzó el límite de {LIMITE_SEG_LICITACIONES // 60} min "
                    f"(se revisaron {revisadas_ahora} nuevas; el resto se revisará en la próxima ejecución)"
                )
                print(f"AVISO: {AVISOS_LICITACIONES[-1]}", file=sys.stderr)
                print(f"  {saltadas} ya revisadas antes (omitidas), {revisadas_ahora} revisadas ahora.")
                return list(resultados.values())
            try:
                try:
                    detalle = obtener_detalle(codigo)
                except LimiteExcedido:
                    time.sleep(ESPERA_429_DETALLE)
                    detalle = obtener_detalle(codigo)
                seguidos_429 = 0
            except LimiteExcedido:
                seguidos_429 += 1
                if seguidos_429 >= MAX_429_SEGUIDOS:
                    AVISOS_LICITACIONES.append(
                        "Licitaciones incompleta: la API respondió 429 (límite de uso) repetidamente y se "
                        f"detuvo la revisión tras {revisadas_ahora} nuevas; el resto se revisará en la próxima ejecución"
                    )
                    print(f"AVISO: {AVISOS_LICITACIONES[-1]}", file=sys.stderr)
                    return list(resultados.values())
                continue
            except requests.RequestException as e:
                print(f"  aviso: no se pudo obtener detalle de {codigo}: {_sin_ticket(e)}", file=sys.stderr)
                time.sleep(PAUSA_ENTRE_LLAMADAS)
                continue

            if detalle:
                revisadas_ahora += 1
                if registro is not None:
                    registro["revisadas"][codigo] = memoria.hoy()
                match = evaluar_licitacion(detalle)
                if match:
                    resultados[codigo] = match
                    print(f"  MATCH licitación: {codigo} - {match['nombre'][:60]}")

            time.sleep(PAUSA_ENTRE_LLAMADAS)

    print(f"  {saltadas} ya revisadas antes (omitidas), {revisadas_ahora} revisadas ahora.")
    return list(resultados.values())


def obtener_compra_agil_seguro():
    """Intenta obtener Compra Ágil vía la API oficial; si algo falla (ticket
    sin permiso, cuota agotada, error del servicio, etc.) no debe tumbar
    todo el envío de correo — solo se registra el error y se sigue sin
    esa sección."""
    if not INCLUIR_COMPRA_AGIL:
        print("Compra Ágil desactivada (INCLUIR_COMPRA_AGIL=0).")
        return [], None

    try:
        import alerta_compra_agil
        resultados = alerta_compra_agil.obtener_compra_agil()
        if alerta_compra_agil.ADVERTENCIAS:
            return resultados, "Compra Ágil incompleta hoy: " + "; ".join(alerta_compra_agil.ADVERTENCIAS)
        return resultados, None
    except Exception as e:
        mensaje = f"No se pudo obtener Compra Ágil hoy (el scraper falló): {_sin_ticket(e)}"
        print(f"AVISO: {mensaje}", file=sys.stderr)
        return [], mensaje


def _tabla_licitaciones(resultados):
    if not resultados:
        return "<p>Sin coincidencias de Licitaciones hoy.</p>"
    filas = "".join(
        f"""
        <tr>
          <td style="padding:8px;border:1px solid #ddd;"><a href="{r['url']}">{r['codigo']}</a></td>
          <td style="padding:8px;border:1px solid #ddd;">{r['nombre']}</td>
          <td style="padding:8px;border:1px solid #ddd;">{r['organismo']}</td>
          <td style="padding:8px;border:1px solid #ddd;">{r['comuna']} ({r['region']})</td>
          <td style="padding:8px;border:1px solid #ddd;">{r['fecha_cierre']}</td>
        </tr>"""
        for r in resultados
    )
    return f"""
      <table style="border-collapse:collapse;width:100%;">
        <tr style="background:#f2f2f2;">
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Código</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Nombre</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Organismo</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Comuna / Región</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Cierre</th>
        </tr>
        {filas}
      </table>
    """


def _tabla_compra_agil(resultados):
    if not resultados:
        return "<p>Sin coincidencias de Compra Ágil hoy.</p>"
    filas = "".join(
        f"""
        <tr>
          <td style="padding:8px;border:1px solid #ddd;"><a href="{r['url']}">{r['codigo'] or '-'}</a></td>
          <td style="padding:8px;border:1px solid #ddd;">{r['nombre']}</td>
          <td style="padding:8px;border:1px solid #ddd;">{r['organismo']}</td>
          <td style="padding:8px;border:1px solid #ddd;">{r['region']}</td>
          <td style="padding:8px;border:1px solid #ddd;">{r['presupuesto']}</td>
          <td style="padding:8px;border:1px solid #ddd;">{r['fecha_cierre']}</td>
        </tr>"""
        for r in resultados
    )
    return f"""
      <table style="border-collapse:collapse;width:100%;">
        <tr style="background:#f2f2f2;">
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Código</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Nombre</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Organismo</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Región</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Presupuesto</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Cierre</th>
        </tr>
        {filas}
      </table>
    """


def construir_cuerpo_html(fecha_legible, licitaciones, compra_agil, error_compra_agil,
                          resumen_agil="", descartadas_agil=(), aviso_licitaciones=None):
    diagnostico_agil = ""
    if resumen_agil:
        descartes = ""
        if descartadas_agil:
            lista = "; ".join(n[:70] for n in list(descartadas_agil)[:10])
            extra = f" (y {len(descartadas_agil) - 10} más)" if len(descartadas_agil) > 10 else ""
            descartes = f"<br>Descartadas por el filtro de palabras: {lista}{extra}."
        diagnostico_agil = f'<p style="color:#777;font-size:12px;">{resumen_agil}{descartes}</p>'
    aviso_lic = ""
    if aviso_licitaciones:
        aviso_lic = f"""
        <p style="background:#fff3cd;border:1px solid #ffe69c;padding:10px;border-radius:4px;">
          ⚠️ {aviso_licitaciones}. Revisa manualmente en
          <a href="https://www.mercadopublico.cl">mercadopublico.cl</a>.
        </p>
        """
    aviso_agil = ""
    if error_compra_agil:
        aviso_agil = f"""
        <p style="background:#fff3cd;border:1px solid #ffe69c;padding:10px;border-radius:4px;">
          ⚠️ {error_compra_agil}. Revisa manualmente en
          <a href="https://buscador.mercadopublico.cl/compra-agil">buscador.mercadopublico.cl/compra-agil</a>.
        </p>
        """

    return f"""
    <html><body style="font-family:Arial,sans-serif;">
      <h2>Alertas Mercado Público — {fecha_legible}</h2>

      <h3>Licitaciones ({len(licitaciones)})</h3>
      {aviso_lic}
      {_tabla_licitaciones(licitaciones)}

      <h3 style="margin-top:24px;">Compra Ágil ({len(compra_agil)})</h3>
      {aviso_agil}
      {_tabla_compra_agil(compra_agil)}
      {diagnostico_agil}

      <p style="color:#777;font-size:12px;margin-top:16px;">
        Licitaciones: datos oficiales vía api.mercadopublico.cl.<br>
        Compra Ágil: datos oficiales vía api2.mercadopublico.cl — si algo se
        ve raro, verifica directo en el sitio.
      </p>
    </body></html>
    """


def enviar_correo(asunto, cuerpo_html):
    destinatarios = [d.strip() for d in EMAIL_TO.split(",") if d.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(destinatarios)
    msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_FROM, destinatarios, msg.as_string())


def main():
    # Hora de Chile continental aproximada (UTC-4 / UTC-3 según horario de verano).
    # Consultamos hoy Y ayer (ver obtener_licitaciones) para no perder
    # licitaciones publicadas después de la hora en que corrió el script.
    # Fechas según el reloj de Chile (no UTC): pasadas las 21:00 en Chile ya es
    # "mañana" en UTC, y pedir el listado de un día que aún no existe da error 500.
    hoy_cl = datetime.now(ZoneInfo("America/Santiago"))
    ayer_cl = hoy_cl - timedelta(days=1)
    fechas_api = [hoy_cl.strftime("%d%m%Y"), ayer_cl.strftime("%d%m%Y")]
    fecha_legible = hoy_cl.strftime("%d-%m-%Y")

    registro = memoria.cargar()
    print(f"Memoria: {len(registro['revisadas'])} licitaciones revisadas y "
          f"{len(registro['notificadas'])} avisos anteriores.")

    print("=== Compra Ágil (API oficial) ===")
    compra_agil, error_compra_agil = obtener_compra_agil_seguro()
    # Solo las que no se avisaron antes
    compra_agil_nueva = [c for c in compra_agil if c["codigo"] not in registro["notificadas"]]
    ya_avisadas = len(compra_agil) - len(compra_agil_nueva)

    print(f"=== Licitaciones ({' y '.join(fechas_api)}) ===")
    try:
        licitaciones = obtener_licitaciones(fechas_api, registro)
    except requests.RequestException as e:
        print(f"Error consultando licitaciones: {_sin_ticket(e)}", file=sys.stderr)
        licitaciones = []
        AVISOS_LICITACIONES.append(f"No se pudieron consultar las licitaciones hoy: {_sin_ticket(e)}")
    licitaciones = [l for l in licitaciones if l["codigo"] not in registro["notificadas"]]
    aviso_licitaciones = "; ".join(AVISOS_LICITACIONES) or None

    total = len(licitaciones) + len(compra_agil_nueva)
    asunto = f"Alertas Mercado Público — {fecha_legible} ({total} coincidencias)"
    try:
        import alerta_compra_agil as _ca
        resumen_agil, descartadas_agil = _ca.RESUMEN, list(_ca.DESCARTADAS)
    except Exception:
        resumen_agil, descartadas_agil = "", []
    if resumen_agil and ya_avisadas:
        resumen_agil += f" {ya_avisadas} ya se habían avisado antes."
    cuerpo = construir_cuerpo_html(fecha_legible, licitaciones, compra_agil_nueva, error_compra_agil, resumen_agil, descartadas_agil, aviso_licitaciones)

    print("Enviando correo...")
    enviar_correo(asunto, cuerpo)

    # La memoria se guarda DESPUÉS de enviar: si el correo falla, la próxima
    # ejecución vuelve a intentarlo con todo lo pendiente.
    for item in list(compra_agil_nueva) + list(licitaciones):
        registro["notificadas"][item["codigo"]] = memoria.hoy()
    memoria.guardar(registro)
    print("Listo.")


if __name__ == "__main__":
    main()
