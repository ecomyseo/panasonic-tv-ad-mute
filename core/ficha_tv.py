"""
Lo que enseña la ficha de un programa en la tele (y en el móvil): título, una línea de datos (nota, en qué minuto
vas o a qué hora es, canal), la sinopsis, el cartel y el reparto, la dirección, la música y quién presenta.

El reparto y lo demás salen de la propia guía (dobleM, datos de Movistar+): vienen al final de la descripción como
líneas «· Reparto: ...», «· Dirección: ...», y epg.py los separa en «creditos».
"""

import time

# Lo que cabe en la tarjeta de la tele, en este orden (el móvil los enseña todos)
EN_LA_TELE = ("Reparto", "Presenta", "Dirección", "Música", "Guion")
ACTORES_EN_LA_TELE = 6


def minuto(programa, ahora=None):
    """'minuto 37 de 95' si se está emitiendo; '' si no."""
    if not programa or not programa.get("inicio_ts"):
        return ""
    ahora = ahora or time.time()
    inicio, fin = float(programa["inicio_ts"]), float(programa["fin_ts"])
    if not inicio <= ahora < fin:
        return ""
    return f"minuto {int((ahora - inicio) // 60) + 1} de {max(1, round((fin - inicio) / 60))}"


def pie(creditos, maximo=300) -> str:
    partes = []
    for clave in EN_LA_TELE:
        valor = (creditos or {}).get(clave)
        if not valor:
            continue
        if clave == "Reparto":
            nombres = [n.strip() for n in valor.rstrip(".").split(",") if n.strip()]
            valor = ", ".join(nombres[:ACTORES_EN_LA_TELE]) + ("…" if len(nombres) > ACTORES_EN_LA_TELE else "")
        partes.append(f"{clave}: {valor.rstrip('.')}")
    texto = " · ".join(partes)
    return texto if len(texto) <= maximo else texto[:maximo - 1] + "…"


def tarjeta(programa, canal="", ficha=None, ahora=None) -> dict:
    """Los textos de la tarjeta. `programa` en el formato público de epg.py; `ficha` la de media_info (opcional)."""
    programa = programa or {}
    ficha = ficha or {}
    titulo = ficha.get("title") or programa.get("titulo") or ""
    if ficha.get("year"):
        titulo += f" ({ficha['year']})"
    nota = ficha.get("rating") or (f"★ {programa['nota']:.1f}/10" if programa.get("nota") else "")
    cuando = minuto(programa, ahora) or (f"{programa['inicio']}–{programa['fin']}" if programa.get("inicio") else "")
    return {
        "titulo": titulo,
        "detalle": " · ".join(x for x in (nota, cuando, canal) if x),
        "mensaje": ficha.get("synopsis") or programa.get("descripcion") or "",
        "imagen": ficha.get("poster_url") or programa.get("imagen") or "",
        "pie": pie(programa.get("creditos")),
    }
