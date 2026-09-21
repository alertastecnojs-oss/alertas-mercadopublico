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
    "vigilancia", "enlace", "enlaces",
    "anpr", "cctv", "televigilancia",
    "telecomunicacion", "telecomunicaciones",
]

# Palabras demasiado genéricas en el lenguaje de compras públicas chilenas
# ("red de salud", "red eléctrica", "cámara de comercio", "cámara de
# inspección de alcantarillado", etc.) — para estas, NO basta con que
# aparezca la palabra sola: también debe aparecer, en el mismo texto,
# al menos una de sus palabras de contexto. Así "cámara" solo cuenta si
# viene acompañada de "seguridad", "vigilancia", "ip", etc.
PALABRAS_CON_CONTEXTO = {
    "camara": ["seguridad", "vigilancia", "ip", "video", "cctv", "monitoreo"],
    "camaras": ["seguridad", "vigilancia", "ip", "video", "cctv", "monitoreo"],
    "red": [
        "inalambrica", "wifi", "datos", "telecomunicacion", "telecomunicaciones",
        "fibra", "radioenlace", "microondas", "internet", "conectividad",
    ],
    "redes": [
        "inalambrica", "wifi", "datos", "telecomunicacion", "telecomunicaciones",
        "fibra", "radioenlace", "microondas", "internet", "conectividad",
    ],
}

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


def _tiene_palabra(texto, palabra):
    return re.search(rf"\b{re.escape(palabra)}\b", texto) is not None


def contiene_palabra_clave(*textos):
    combinado = normalizar(" ".join(t for t in textos if t))

    if any(frase in combinado for frase in FRASES_EXCLUIDAS):
        return False

    for palabra in PALABRAS_CLAVE:
        if _tiene_palabra(combinado, palabra):
            return True

    for palabra, contextos in PALABRAS_CON_CONTEXTO.items():
        if _tiene_palabra(combinado, palabra) and any(_tiene_palabra(combinado, c) for c in contextos):
            return True

    return False


def region_coincide(region_texto):
    region_norm = normalizar(region_texto or "")
    return any(r in region_norm for r in REGIONES_OBJETIVO)
