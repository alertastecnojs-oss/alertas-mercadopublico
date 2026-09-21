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
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from common import contiene_palabra_clave, region_coincide

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
PAUSA_ENTRE_LLAMADAS = 0.15  # segundos, para no saturar la API

# URL pública para ver el detalle de una licitación en el portal
URL_DETALLE = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={codigo}"


def obtener_licitaciones_del_dia(fecha_ddmmaaaa):
    """Trae el listado básico de licitaciones publicadas en la fecha dada."""
    params = {"fecha": fecha_ddmmaaaa, "estado": "publicada", "ticket": MP_TICKET}
    resp = requests.get(API_BASE, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("Listado", []) or []


def obtener_detalle(codigo):
    """Trae el detalle completo de una licitación (región, ítems, etc.)."""
    params = {"codigo": codigo, "ticket": MP_TICKET}
    resp = requests.get(API_BASE, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
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


def obtener_licitaciones(fecha_ddmmaaaa):
    listado_basico = obtener_licitaciones_del_dia(fecha_ddmmaaaa)
    print(f"{len(listado_basico)} licitaciones publicadas hoy. Revisando detalle de cada una...")

    resultados = []
    for item in listado_basico:
        codigo = item.get("CodigoExterno")
        if not codigo:
            continue
        try:
            detalle = obtener_detalle(codigo)
        except requests.RequestException as e:
            print(f"  aviso: no se pudo obtener detalle de {codigo}: {e}", file=sys.stderr)
            time.sleep(PAUSA_ENTRE_LLAMADAS)
            continue

        if detalle:
            match = evaluar_licitacion(detalle)
            if match:
                resultados.append(match)
                print(f"  MATCH licitación: {codigo} - {match['nombre'][:60]}")

        time.sleep(PAUSA_ENTRE_LLAMADAS)

    return resultados


def obtener_compra_agil_seguro():
    """Intenta obtener Compra Ágil vía la API oficial; si algo falla (ticket
    sin permiso, cuota agotada, error del servicio, etc.) no debe tumbar
    todo el envío de correo — solo se registra el error y se sigue sin
    esa sección."""
    if not INCLUIR_COMPRA_AGIL:
        print("Compra Ágil desactivada (INCLUIR_COMPRA_AGIL=0).")
        return [], None

    try:
        from alerta_compra_agil import obtener_compra_agil
        return obtener_compra_agil(), None
    except Exception as e:
        mensaje = f"No se pudo obtener Compra Ágil hoy (el scraper falló): {e}"
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


def construir_cuerpo_html(fecha_legible, licitaciones, compra_agil, error_compra_agil):
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
      {_tabla_licitaciones(licitaciones)}

      <h3 style="margin-top:24px;">Compra Ágil ({len(compra_agil)})</h3>
      {aviso_agil}
      {_tabla_compra_agil(compra_agil)}

      <p style="color:#777;font-size:12px;margin-top:16px;">
        Licitaciones: datos oficiales vía api.mercadopublico.cl.<br>
        Compra Ágil: extraído del buscador público (no hay API oficial para
        este mecanismo) — si algo se ve raro, verifica directo en el sitio.
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

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_FROM, destinatarios, msg.as_string())


def main():
    # Hora de Chile continental aproximada (UTC-4 / UTC-3 según horario de verano).
    # Usamos la fecha UTC del día de ejecución; el workflow ya está programado
    # para correr en horario de mañana en Chile.
    hoy_utc = datetime.now(timezone.utc)
    fecha_api = hoy_utc.strftime("%d%m%Y")
    fecha_legible = hoy_utc.strftime("%d-%m-%Y")

    print(f"=== Licitaciones ({fecha_api}) ===")
    try:
        licitaciones = obtener_licitaciones(fecha_api)
    except requests.RequestException as e:
        print(f"Error consultando licitaciones: {e}", file=sys.stderr)
        licitaciones = []

    print("=== Compra Ágil (API oficial) ===")
    compra_agil, error_compra_agil = obtener_compra_agil_seguro()

    total = len(licitaciones) + len(compra_agil)
    asunto = f"Alertas Mercado Público — {fecha_legible} ({total} coincidencias)"
    cuerpo = construir_cuerpo_html(fecha_legible, licitaciones, compra_agil, error_compra_agil)

    print("Enviando correo...")
    enviar_correo(asunto, cuerpo)
    print("Listo.")


if __name__ == "__main__":
    main()
