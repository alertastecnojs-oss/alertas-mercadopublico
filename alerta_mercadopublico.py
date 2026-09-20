#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alerta diaria de licitaciones de Mercado Público (Chile)
=========================================================

Consulta la API pública de Mercado Público (api.mercadopublico.cl), filtra
las licitaciones publicadas el día de ejecución por:
  - Región del comprador (Maule y/o Ñuble)
  - Palabras clave (en el título, la descripción, o los ítems solicitados)

y envía un correo con el resumen.

Nota importante: la API pública de Mercado Público NO expone "Compra Ágil"
(solo Licitaciones, Trato Directo y Convenio Marco). Para Compra Ágil hay
que seguir revisando el Escritorio de Proveedor con los rubros inscritos.

Configuración: todo se lee desde variables de entorno (ver README.md /
el workflow de GitHub Actions), nunca se hardcodean credenciales aquí.
"""

import os
import sys
import time
import smtplib
import unicodedata
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ---------------------------------------------------------------------------
# Configuración (desde variables de entorno)
# ---------------------------------------------------------------------------

MP_TICKET = os.environ["MP_TICKET"]  # Ticket de api.mercadopublico.cl

EMAIL_FROM = os.environ["EMAIL_FROM"]           # cuenta que envía (ej: Gmail)
EMAIL_APP_PASSWORD = os.environ["EMAIL_APP_PASSWORD"]  # contraseña de aplicación
EMAIL_TO = os.environ["EMAIL_TO"]               # destinatario(s), separados por coma
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

# Regiones a monitorear (coincidencia flexible, sin tildes, en minúsculas)
REGIONES_OBJETIVO = ["maule", "nuble"]

# Palabras clave a buscar (sin tildes, en minúsculas)
PALABRAS_CLAVE = [
    "camara", "camaras", "vigilancia", "enlace", "enlaces",
    "anpr", "cctv", "televigilancia", "red", "redes",
    "telecomunicacion", "telecomunicaciones",
]

API_BASE = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
TIMEOUT = 20
PAUSA_ENTRE_LLAMADAS = 0.15  # segundos, para no saturar la API

# URL pública para ver el detalle de una licitación en el portal
URL_DETALLE = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={codigo}"


def normalizar(texto):
    """Minúsculas y sin tildes/ñ, para comparar de forma flexible."""
    if not texto:
        return ""
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto


def contiene_palabra_clave(*textos):
    combinado = normalizar(" ".join(t for t in textos if t))
    return any(palabra in combinado for palabra in PALABRAS_CLAVE)


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


def region_coincide(region_texto):
    region_norm = normalizar(region_texto)
    return any(r in region_norm for r in REGIONES_OBJETIVO)


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


def construir_cuerpo_html(resultados, fecha_legible):
    if not resultados:
        return (
            f"<p>No se encontraron licitaciones nuevas del {fecha_legible} que coincidan "
            f"con tus rubros/palabras clave en la Región del Maule o Ñuble.</p>"
        )

    filas = ""
    for r in resultados:
        filas += f"""
        <tr>
          <td style="padding:8px;border:1px solid #ddd;"><a href="{r['url']}">{r['codigo']}</a></td>
          <td style="padding:8px;border:1px solid #ddd;">{r['nombre']}</td>
          <td style="padding:8px;border:1px solid #ddd;">{r['organismo']}</td>
          <td style="padding:8px;border:1px solid #ddd;">{r['comuna']} ({r['region']})</td>
          <td style="padding:8px;border:1px solid #ddd;">{r['fecha_cierre']}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;">
      <h2>Licitaciones nuevas — {fecha_legible}</h2>
      <p>{len(resultados)} coincidencia(s) en Región del Maule / Ñuble:</p>
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
      <p style="color:#777;font-size:12px;margin-top:16px;">
        Recuerda: Compra Ágil no está disponible vía API — revisa tus rubros inscritos
        en el Escritorio de Proveedor de Mercado Público para esas oportunidades.
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

    print(f"Consultando licitaciones publicadas el {fecha_api}...")
    try:
        listado_basico = obtener_licitaciones_del_dia(fecha_api)
    except requests.RequestException as e:
        print(f"Error consultando el listado diario: {e}", file=sys.stderr)
        sys.exit(1)

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
                print(f"  MATCH: {codigo} - {match['nombre'][:60]}")

        time.sleep(PAUSA_ENTRE_LLAMADAS)

    asunto = f"Alertas Mercado Público — {fecha_legible} ({len(resultados)} coincidencias)"
    cuerpo = construir_cuerpo_html(resultados, fecha_legible)

    print("Enviando correo...")
    enviar_correo(asunto, cuerpo)
    print("Listo.")


if __name__ == "__main__":
    main()
