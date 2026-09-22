#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compra Ágil — vía la API oficial api2.mercadopublico.cl
==========================================================

ChileCompra lanzó en mayo de 2026 una API oficial para Compra Ágil
(v2), con ticket de acceso, filtros por región/palabra clave/estado/
fecha y paginación. Reemplaza al método anterior (navegador real
contra el buscador web), que ya no es necesario.

Documentación oficial: https://www.chilecompra.cl/api/
Ticket: se obtiene en el mismo lugar que el ticket de
api.mercadopublico.cl (botón "Pide tu ticket", con Clave Única). Si el
ticket que ya usas para Licitaciones (MP_TICKET) no funciona aquí,
pide uno nuevo en ese mismo portal — probablemente sea el mismo, pero
no está garantizado por la documentación.
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from common import PALABRAS_CLAVE, PALABRAS_CON_CONTEXTO, REGIONES_OBJETIVO, contiene_palabra_clave

BASE_URL = "https://api2.mercadopublico.cl"
TICKET = os.environ.get("MP_TICKET_COMPRA_AGIL") or os.environ.get("MP_TICKET")
TIMEOUT = 20
TAMANO_PAGINA = 50  # máximo permitido por la API
PAUSA_ENTRE_LLAMADAS = 0.5

# Términos a buscar en la API: las palabras "seguras" MÁS las palabras que
# requieren contexto (camara, camaras, red, redes, vigilancia) — si no se
# buscan estas últimas, la API nunca las devuelve y no hay nada que
# filtrar localmente después. contiene_palabra_clave() se sigue encargando
# de exigir el contexto real (ver common.py) sobre lo que la API devuelve.
TERMINOS_BUSQUEDA = list(dict.fromkeys(PALABRAS_CLAVE + list(PALABRAS_CON_CONTEXTO.keys())))

URL_DETALLE = "https://buscador.mercadopublico.cl/compra-agil/detalle/{codigo}"

# Códigos de región de la API (1 a 16) para las regiones configuradas en
# common.py — coinciden con los mismos códigos usados en todo Mercado
# Público (7 = Maule, 16 = Ñuble).
_REGIONES_PARAM = ",".join(str(c) for c in REGIONES_OBJETIVO.values())


def _headers():
    return {"ticket": TICKET}


def _buscar_pagina(keyword, fecha_desde, fecha_hasta, numero_pagina):
    params = {
        "q": keyword,
        "region": _REGIONES_PARAM,
        "estado": "publicada",
        "publicado_desde": fecha_desde,
        "publicado_hasta": fecha_hasta,
        "tamano_pagina": TAMANO_PAGINA,
        "numero_pagina": numero_pagina,
        "ordenar_por": "FechaPublicacion",
    }
    resp = requests.get(
        f"{BASE_URL}/v2/compra-agil", headers=_headers(), params=params, timeout=TIMEOUT
    )
    if resp.status_code == 429:
        print("  aviso: cuota diaria de la API de Compra Ágil agotada (429).", file=sys.stderr)
        return [], 1, 1
    resp.raise_for_status()
    data = resp.json()
    if data.get("success") != "OK":
        errores = data.get("errors") or []
        raise RuntimeError(f"API Compra Ágil respondió error: {errores}")

    payload = data.get("payload") or {}
    items = payload.get("items", []) or []
    paginacion = payload.get("paginacion", {}) or {}
    return items, paginacion.get("numero_pagina", 1), paginacion.get("total_paginas", 1)


def obtener_compra_agil():
    """Busca, para cada palabra clave configurada, las Compras Ágiles
    publicadas hoy en las regiones objetivo. Devuelve una lista de dicts
    sin duplicados (por código)."""
    if not TICKET:
        raise RuntimeError(
            "No hay ticket configurado para la API de Compra Ágil "
            "(variable MP_TICKET o MP_TICKET_COMPRA_AGIL)."
        )

    ahora = datetime.now(timezone.utc)
    hace_24h = ahora - timedelta(hours=24)
    fecha_desde = hace_24h.strftime("%Y-%m-%dT%H:%M:%SZ")
    fecha_hasta = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")

    vistos = {}  # codigo -> dict, para evitar duplicados entre palabras clave

    for palabra in TERMINOS_BUSQUEDA:
        print(f"Compra Ágil: buscando '{palabra}'...")
        pagina = 1
        while True:
            items, pagina_actual, total_paginas = _buscar_pagina(palabra, fecha_desde, fecha_hasta, pagina)
            for item in items:
                codigo = item.get("codigo")
                if not codigo or codigo in vistos:
                    continue
                nombre = item.get("nombre", "") or ""
                # El endpoint de listado ya filtró por 'q', pero igual
                # verificamos localmente por si el match del buscador
                # es más amplio de lo esperado (ej. coincide en otro campo).
                if not contiene_palabra_clave(nombre):
                    continue

                institucion = item.get("institucion") or {}
                montos = item.get("montos") or {}
                fechas = item.get("fechas") or {}
                estado = item.get("estado") or {}

                vistos[codigo] = {
                    "codigo": codigo,
                    "nombre": nombre,
                    "organismo": institucion.get("organismo_comprador", ""),
                    "region": institucion.get("nombre_region", ""),
                    "presupuesto": f"${montos.get('monto_disponible_clp', 0):,}".replace(",", ".")
                    if montos.get("monto_disponible_clp") is not None
                    else "No informado",
                    "fecha_cierre": fechas.get("fecha_cierre", ""),
                    "estado": estado.get("glosa", ""),
                    "url": URL_DETALLE.format(codigo=codigo),
                }
                print(f"  MATCH: {codigo} - {nombre[:60]}")

            if pagina_actual >= total_paginas:
                break
            pagina += 1
            time.sleep(PAUSA_ENTRE_LLAMADAS)

        time.sleep(PAUSA_ENTRE_LLAMADAS)

    return list(vistos.values())


if __name__ == "__main__":
    # Permite probar este script de forma independiente:
    #   python alerta_compra_agil.py
    encontrados = obtener_compra_agil()
    print(f"\nTotal coincidencias Compra Ágil: {len(encontrados)}")
    for r in encontrados:
        print(r)
