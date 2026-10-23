#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memoria entre ejecuciones
=========================

Guarda en un archivo JSON qué ya se vio, para no repetir trabajo ni avisos:

  "revisadas"   -> licitaciones cuyo detalle ya se consultó (se saltan en las
                   siguientes corridas: es lo que más tiempo ahorra).
  "unidades"    -> para cada unidad compradora (el primer número del código de
                   la licitación, ej. 4085 en 4085-46-LE26): si está en tus
                   regiones o no. La región de una unidad no cambia, así que
                   las de otras regiones se saltan sin consultar su detalle
                   (baja de ~900 consultas por corrida a unas pocas decenas).
  "notificadas" -> licitaciones y Compras Ágiles que ya aparecieron en un
                   correo (no se vuelven a avisar).

En GitHub Actions el archivo se conserva entre ejecuciones con actions/cache
(ver .github/workflows/alerta-diaria.yml). Si el archivo no existe (primera
vez, o la caché expiró) se parte de cero: funciona igual, solo que esa vez
puede avisar de cosas ya vistas.
"""

import json
import os
from datetime import date, timedelta

ARCHIVO = os.environ.get(
    "ARCHIVO_ESTADO",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "vistos_mercadopublico.json"),
)
DIAS_RETENCION = 60
DIAS_RETENCION_UNIDADES = 365  # la región de una unidad compradora casi nunca cambia  # pasado este tiempo se olvidan los códigos (el archivo no crece sin límite)


def hoy():
    return date.today().isoformat()


def _vacio():
    return {"revisadas": {}, "notificadas": {}, "unidades": {}}


def cargar():
    try:
        with open(ARCHIVO, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "revisadas": dict(data.get("revisadas", {})),
            "notificadas": dict(data.get("notificadas", {})),
            "unidades": dict(data.get("unidades", {})),
        }
    except (FileNotFoundError, ValueError, AttributeError, TypeError):
        return _vacio()


def guardar(estado):
    limite = (date.today() - timedelta(days=DIAS_RETENCION)).isoformat()
    podado = {
        clave: {c: f for c, f in estado.get(clave, {}).items() if f >= limite}
        for clave in ("revisadas", "notificadas")
    }
    limite_u = (date.today() - timedelta(days=DIAS_RETENCION_UNIDADES)).isoformat()
    podado["unidades"] = {
        u: v for u, v in estado.get("unidades", {}).items()
        if isinstance(v, dict) and v.get("f", "") >= limite_u
    }
    tmp = ARCHIVO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(podado, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, ARCHIVO)
