#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuración y utilidades compartidas por alerta_mercadopublico.py
(Licitaciones, vía API oficial) y alerta_compra_agil.py (Compra Ágil,
vía navegador real contra el buscador público, ya que Compra Ágil no
tiene API pública).

Edita aquí las palabras clave y regiones — ambos scripts las leen de
este mismo lugar.
"""

import unicodedata

# Palabras clave a buscar (sin tildes, en minúsculas). Se normalizan antes
# de comparar, así que no importa cómo las escribas aquí en mayúsculas/tildes,
# pero mantenlas en minúsculas y sin tildes por claridad.
PALABRAS_CLAVE = [
    "camara", "camaras", "vigilancia", "enlace", "enlaces",
    "anpr", "cctv", "televigilancia", "red", "redes",
    "telecomunicacion", "telecomunicaciones",
]

# Regiones a monitorear: nombre normalizado -> código numérico de región
# que usa el buscador de Compra Ágil (VII = Maule, XVI = Ñuble).
REGIONES_OBJETIVO = {
    "maule": 7,
    "nuble": 16,
}


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


def region_coincide(region_texto):
    region_norm = normalizar(region_texto or "")
    return any(r in region_norm for r in REGIONES_OBJETIVO)
