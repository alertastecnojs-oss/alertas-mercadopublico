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

import requests

from common import PALABRAS_CLAVE, PALABRAS_CON_CONTEXTO, REGIONES_OBJETIVO, contiene_palabra_clave_titulo

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

# Avisos de esta corrida (ej. cuota agotada). alerta_mercadopublico.py los
# lee y los muestra en el correo, para que un resultado vacío por error
# no se confunda con "hoy no hubo nada".
ADVERTENCIAS = []
# Diagnóstico de la corrida, para el correo: cuántas Compras Ágiles devolvió
# la API y cuáles descartó el filtro de palabras (common.py).
RESUMEN = ""
DESCARTADAS = []


class CuotaAgotada(Exception):
    """La API respondió 429: se agotó la cuota diaria del ticket."""

# Códigos de región de la API (1 a 16) para las regiones configuradas en
# common.py — coinciden con los mismos códigos usados en todo Mercado
# Público (7 = Maule, 16 = Ñuble).
_REGIONES_PARAM = ",".join(str(c) for c in REGIONES_OBJETIVO.values())


def _headers():
    return {"ticket": TICKET}


def _buscar_pagina(keyword, numero_pagina):
    params = {
        "q": keyword,
        "region": _REGIONES_PARAM,
        "estado": "publicada",
        "tamano_pagina": TAMANO_PAGINA,
        "numero_pagina": numero_pagina,
        "ordenar_por": "FechaPublicacion",
    }
    resp = requests.get(
        f"{BASE_URL}/v2/compra-agil", headers=_headers(), params=params, timeout=TIMEOUT
    )
    if resp.status_code == 429:
        print("  aviso: cuota diaria de la API de Compra Ágil agotada (429).", file=sys.stderr)
        raise CuotaAgotada()
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
    abiertas en las regiones objetivo. Devuelve una lista de dicts sin
    duplicados (por código). Quién ya fue avisado se filtra afuera
    (alerta_mercadopublico.py, con estado.py)."""
    if not TICKET:
        raise RuntimeError(
            "No hay ticket configurado para la API de Compra Ágil "
            "(variable MP_TICKET o MP_TICKET_COMPRA_AGIL)."
        )

    # Sin ventana de fechas: se piden TODAS las Compras Ágiles abiertas
    # ("publicada") que coinciden con cada término. Como el programa recuerda
    # entre ejecuciones cuáles ya avisó (estado.py), no se repiten, y así no
    # dependemos de la hora, de zonas horarias (la API marca con "Z" fechas
    # que en realidad están en hora de Chile) ni de que no falle ninguna
    # ejecución.
    ADVERTENCIAS.clear()
    DESCARTADAS.clear()
    global RESUMEN
    RESUMEN = ""

    vistos = {}  # codigo -> dict, para evitar duplicados entre palabras clave
    devueltas_api = set()  # todo lo que la API devolvió, pase o no el filtro
    descartadas = {}  # codigo -> nombre, lo que el filtro de palabras dejó fuera

    def _cerrar():
        global RESUMEN
        DESCARTADAS.extend(descartadas.values())
        RESUMEN = (
            f"La API devolvió {len(devueltas_api)} Compra(s) Ágil(es) abiertas en Maule/Ñuble "
            f"para tus términos de búsqueda; {len(vistos)} pasaron el filtro de palabras."
        )
        print(RESUMEN)

    for palabra in TERMINOS_BUSQUEDA:
        print(f"Compra Ágil: buscando '{palabra}'...")
        pagina = 1
        while True:
            try:
                items, pagina_actual, total_paginas = _buscar_pagina(palabra, pagina)
            except CuotaAgotada:
                ADVERTENCIAS.append(
                    "Se agotó la cuota diaria de la API de Compra Ágil (HTTP 429): "
                    f"la búsqueda quedó incompleta (se alcanzó a revisar hasta '{palabra}')"
                )
                _cerrar()
                return list(vistos.values())
            print(f"  '{palabra}' pág. {pagina}: {len(items)} resultado(s) de la API")
            for item in items:
                codigo = item.get("codigo")
                if not codigo:
                    continue
                devueltas_api.add(codigo)
                if codigo in vistos:
                    continue
                nombre = item.get("nombre", "") or ""
                # El endpoint de listado ya filtró por 'q', pero igual
                # verificamos localmente por si el match del buscador
                # es más amplio de lo esperado (ej. coincide en otro campo).
                if not contiene_palabra_clave_titulo(nombre):
                    descartadas[codigo] = nombre
                    print(f"  descartada por filtro: {codigo} - {nombre[:70]}")
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

    _cerrar()
    return list(vistos.values())


if __name__ == "__main__":
    # Permite probar este script de forma independiente:
    #   python alerta_compra_agil.py
    encontrados = obtener_compra_agil()
    print(f"\nTotal coincidencias Compra Ágil: {len(encontrados)}")
    for r in encontrados:
        print(r)
