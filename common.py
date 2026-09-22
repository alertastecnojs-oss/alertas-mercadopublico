#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuración y utilidades compartidas por alerta_mercadopublico.py
(Licitaciones, vía API oficial) y alerta_compra_agil.py (Compra Ágil,
también vía API oficial).

Edita aquí las palabras clave y regiones — ambos scripts las leen de
este mismo lugar.
"""

import re
import unicodedata

# Palabras clave "seguras" — lo bastante específicas como para no
# necesitar contexto adicional. Coinciden como PALABRA COMPLETA (no
# subcadena): "cctv" no matchea "cctvx", etc.
PALABRAS_CLAVE = [
    "enlace", "enlaces",
    "anpr", "cctv", "televigilancia",
    "telecomunicacion", "telecomunicaciones",
]

# Palabras demasiado genéricas en el lenguaje de compras públicas chilenas
# ("red de salud", "servicio de vigilancia y seguridad" = guardias, no
# cámaras; "cámara de comercio", equipos con "monitoreo" clínico, etc.)
# — para estas, no basta con que aparezca la palabra sola: también debe
# aparecer una palabra de CONTEXTO cerca (a un máximo de VENTANA_PALABRAS
# palabras de distancia, no en cualquier parte del texto — una licitación
# puede tener varios ítems sin relación entre sí, y no queremos que "red"
# en un ítem "matchee" con "datos" de otro ítem distinto).
VENTANA_PALABRAS = 6

PALABRAS_CON_CONTEXTO = {
    "camara": ["seguridad", "vigilancia", "ip", "cctv", "video"],
    "camaras": ["seguridad", "vigilancia", "ip", "cctv", "video"],
    "red": [
        "inalambrica", "wifi", "telecomunicacion", "telecomunicaciones",
        "fibra", "radioenlace", "microondas",
    ],
    "redes": [
        "inalambrica", "wifi", "telecomunicacion", "telecomunicaciones",
        "fibra", "radioenlace", "microondas",
    ],
    # "vigilancia" sola es ambigua: en compras públicas casi siempre
    # significa GUARDIAS DE SEGURIDAD (personas), no cámaras. Solo cuenta
    # si aparece cerca de una palabra que sí indica video-vigilancia.
    "vigilancia": ["camara", "camaras", "cctv", "video", "electronica", "ip"],
}

# Frases exactas que SIEMPRE cuentan como match, sin pasar por la lógica
# de ventana de palabras — para casos legítimos donde la palabra de
# contexto (ej. "datos") es en general demasiado genérica para usarla
# como contexto libre, pero la frase completa sí es inequívoca.
FRASES_INCLUIDAS = [
    "red de datos", "redes de datos", "cableado estructurado",
]

# Frases que, si aparecen, DESCARTAN el resultado aunque haya matcheado
# una palabra clave — casos puntuales que se van agregando a medida que
# aparecen falsos positivos nuevos (sin tildes, minúsculas, se buscan
# como subcadena tras normalizar).
FRASES_EXCLUIDAS = [
    "vigilancia epidemiologica", "vigilancia sanitaria",
    "vigilancia ambiental", "vigilancia nutricional",
]

# Regiones a monitorear: nombre normalizado -> código numérico de región
# que usa Mercado Público en todas sus APIs (VII = Maule, XVI = Ñuble).
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


def _tokenizar(texto):
    return re.findall(r"[a-z0-9]+", texto)


def contiene_palabra_clave(*textos):
    combinado = normalizar(" ".join(t for t in textos if t))

    if any(frase in combinado for frase in FRASES_EXCLUIDAS):
        return False

    if any(frase in combinado for frase in FRASES_INCLUIDAS):
        return True

    tokens = _tokenizar(combinado)
    token_set = set(tokens)

    for palabra in PALABRAS_CLAVE:
        if palabra in token_set:
            return True

    for palabra, contextos in PALABRAS_CON_CONTEXTO.items():
        contextos_set = set(contextos)
        for i, t in enumerate(tokens):
            if t != palabra:
                continue
            ventana = tokens[max(0, i - VENTANA_PALABRAS): i + VENTANA_PALABRAS + 1]
            if any(c in ventana for c in contextos_set):
                return True

    return False


def region_coincide(region_texto):
    region_norm = normalizar(region_texto or "")
    return any(r in region_norm for r in REGIONES_OBJETIVO)
