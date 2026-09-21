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

import re
import unicodedata

# Palabras clave a buscar (sin tildes, en minúsculas). Se normalizan antes
# de comparar, así que no importa cómo las escribas aquí en mayúsculas/tildes,
# pero mantenlas en minúsculas y sin tildes por claridad.
#
# IMPORTANTE: la coincidencia es por PALABRA COMPLETA, no por subcadena.
# "camara" hace match con "cámaras de seguridad" pero NO con "camarógrafo"
# ni con nada que no sea exactamente esa palabra (separada por espacios,
# signos de puntuación, etc.).
PALABRAS_CLAVE = [
    "camara", "camaras", "vigilancia", "enlace", "enlaces",
    "anpr", "cctv", "televigilancia", "red", "redes",
    "telecomunicacion", "telecomunicaciones",
]

# Frases que, si aparecen, DESCARTAN el resultado aunque haya matcheado
# una palabra clave — para los falsos positivos típicos de "red" y
# "camara" en el lenguaje de compras públicas chilenas (sin tildes,
# minúsculas, se buscan como subcadena tras normalizar).
FRASES_EXCLUIDAS = [
    # "red" en sentido de red de salud / vial / servicios, no telecom
    "red de salud", "red asistencial", "red hospitalaria",
    "red vial", "red de agua potable", "red de alcantarillado",
    "red educacional", "red de proteccion", "red sename",
    # "camara" en sentido de obra civil / institucional, no cámara de video
    "camara de inspeccion", "camara de alcantarillado", "camara septica",
    "camara de comercio", "camara de diputados", "camara frigorifica",
    "camara de gas", "camara chica",
    # "vigilancia" en sentido de salud/ambiente, no seguridad
    "vigilancia epidemiologica", "vigilancia sanitaria",
    "vigilancia ambiental", "vigilancia nutricional",
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

    if any(frase in combinado for frase in FRASES_EXCLUIDAS):
        return False

    for palabra in PALABRAS_CLAVE:
        if re.search(rf"\b{re.escape(palabra)}\b", combinado):
            return True
    return False


def region_coincide(region_texto):
    region_norm = normalizar(region_texto or "")
    return any(r in region_norm for r in REGIONES_OBJETIVO)
