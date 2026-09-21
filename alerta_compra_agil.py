#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compra Ágil — extracción vía navegador real (Playwright)
=========================================================

Compra Ágil NO tiene API pública (ni api.mercadopublico.cl ni la API OCDS
la exponen). La única vía pública para revisarla es el buscador web:

    https://buscador.mercadopublico.cl/compra-agil

Este script controla un navegador Chromium real (headless) para navegar
ese buscador, filtrando por región y por el día de hoy, y extrae los
resultados del HTML.

⚠️ Importante — esto es más frágil que una API oficial:
- Si ChileCompra rediseña esa página (cambia textos o estructura), este
  script puede dejar de funcionar y hay que ajustarlo.
- Usa el sitio tal como lo usaría cualquier visitante (sin saltarse
  ningún control de acceso ni usar endpoints no documentados), pero
  no hay garantía de que el sitio no bloquee tráfico automatizado en
  el futuro.
- No pagina de forma agresiva: solo revisa el día de hoy por región,
  que en la práctica son pocos resultados.

Este módulo expone obtener_compra_agil(), usada por
alerta_mercadopublico.py para incluir estos resultados en el mismo correo.
"""

import re
import sys
from datetime import datetime, timezone

from common import PALABRAS_CLAVE, REGIONES_OBJETIVO, contiene_palabra_clave

BASE_URL = "https://buscador.mercadopublico.cl/compra-agil"
URL_DETALLE = "https://buscador.mercadopublico.cl/compra-agil/detalle/{codigo}"
TIMEOUT_MS = 30000
MAX_PAGINAS_POR_REGION = 15  # tope de seguridad para no paginar sin fin


def _parsear_tarjeta(texto):
    """Convierte el innerText de una tarjeta de resultado en un dict."""
    # Código: patrón típico de Compra Ágil, termina en -COT + año (2 dígitos)
    m_codigo = re.search(r"[\dA-Za-z]+-\d+-COT\d{2}", texto)
    codigo = m_codigo.group(0) if m_codigo else None

    lineas = [l.strip() for l in texto.split("\n") if l.strip()]

    # El nombre es la línea siguiente al código
    nombre = ""
    if codigo and codigo in lineas:
        idx = lineas.index(codigo)
        if idx + 1 < len(lineas):
            nombre = lineas[idx + 1]

    def _valor_tras(etiqueta, offset=1):
        for i, l in enumerate(lineas):
            if l == etiqueta and i + offset < len(lineas):
                return lineas[i + offset]
        return ""

    fecha_cierre = _valor_tras("Finaliza el", offset=1)
    presupuesto = _valor_tras("Presupuesto estimado", offset=1)

    # El organismo comprador suele ser la línea antes de "Recibiendo
    # cotizaciones" / el estado final, y después del presupuesto.
    organismo = ""
    for i, l in enumerate(lineas):
        if l.startswith("Presupuesto estimado"):
            # busca la siguiente línea que no sea el monto ni vacía
            for j in range(i + 2, len(lineas)):
                if lineas[j] and not lineas[j].startswith("Recibiendo") and "Revisar detalle" not in lineas[j]:
                    organismo = lineas[j]
                    break
            break

    return {
        "codigo": codigo,
        "nombre": nombre,
        "organismo": organismo,
        "fecha_cierre": fecha_cierre,
        "presupuesto": presupuesto,
        "url": URL_DETALLE.format(codigo=codigo) if codigo else BASE_URL,
    }


def _obtener_pagina(page, region_codigo, fecha_str, numero_pagina):
    url = (
        f"{BASE_URL}?date_from={fecha_str}&date_to={fecha_str}"
        f"&order_by=recent&page_number={numero_pagina}&region={region_codigo}&status=2"
    )
    page.goto(url, timeout=TIMEOUT_MS)
    try:
        page.wait_for_selector(
            "text=Revisar detalle, text=No se encontraron resultados",
            timeout=TIMEOUT_MS,
        )
    except Exception:
        pass

    if page.locator("text=No se encontraron resultados").count() > 0:
        return []

    tarjetas = []
    enlaces = page.locator("a:has-text('Revisar detalle')")
    total = enlaces.count()
    for i in range(total):
        try:
            contenedor = enlaces.nth(i).locator(
                "xpath=ancestor::*[contains(@class,'MuiPaper-root')][1]"
            )
            texto = contenedor.inner_text(timeout=5000)
            tarjetas.append(_parsear_tarjeta(texto))
        except Exception as e:
            print(f"  aviso: no se pudo leer una tarjeta: {e}", file=sys.stderr)
    return tarjetas


def obtener_compra_agil():
    """Devuelve la lista de Compra Ágil de hoy, en las regiones y con las
    palabras clave configuradas en common.py. Requiere Playwright con
    Chromium instalado."""
    from playwright.sync_api import sync_playwright

    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resultados = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for nombre_region, codigo_region in REGIONES_OBJETIVO.items():
            print(f"Compra Ágil: revisando región '{nombre_region}' (código {codigo_region})...")
            pagina_num = 1
            while pagina_num <= MAX_PAGINAS_POR_REGION:
                tarjetas = _obtener_pagina(page, codigo_region, hoy, pagina_num)
                if not tarjetas:
                    break
                for t in tarjetas:
                    if contiene_palabra_clave(t["nombre"]):
                        t["region"] = nombre_region
                        resultados.append(t)
                        print(f"  MATCH: {t['codigo']} - {t['nombre'][:60]}")
                pagina_num += 1

        browser.close()

    return resultados


if __name__ == "__main__":
    # Permite probar este script de forma independiente:
    #   python alerta_compra_agil.py
    encontrados = obtener_compra_agil()
    print(f"\nTotal coincidencias Compra Ágil: {len(encontrados)}")
    for r in encontrados:
        print(r)
