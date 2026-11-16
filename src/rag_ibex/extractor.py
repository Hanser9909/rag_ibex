"""Extrae secciones de informes anuales en PDF.

Estrategia: leer el índice impreso para saber qué secciones hay, y luego
buscar cada título dentro del documento para saber dónde empieza de verdad.

Así no dependemos de los números del índice (la numeración impresa no
coincide con las páginas del PDF, y en Iberdrola ni siquiera es constante)
ni de los marcadores del PDF (rotos en Santander: 0 de 360 resuelven).
"""

import re
import unicodedata
from dataclasses import dataclass

import pymupdf


@dataclass
class Seccion:
    """Un trozo del informe: una sección con su texto y de dónde salió."""

    empresa: str
    titulo: str
    pagina_inicio: int  # página física del PDF, empezando en 1
    pagina_fin: int
    texto: str

    @property
    def n_caracteres(self) -> int:
        return len(self.texto)

    def __repr__(self) -> str:
        return (
            f"Seccion({self.empresa}, pp.{self.pagina_inicio}-{self.pagina_fin}, "
            f"{self.n_caracteres:,} chars, {self.titulo[:45]!r})"
        )


# --------------------------------------------------------------------------
# Normalización
# --------------------------------------------------------------------------

def normalizar(texto: str) -> str:
    """Deja el texto en una forma comparable.

    Unifica los espacios raros (los PDF usan \\xa0 a menudo), colapsa los
    saltos de línea y pasa a minúsculas. Hace falta porque un título en el
    índice y el mismo título en su página casi nunca vienen escritos igual.
    """
    texto = unicodedata.normalize("NFKC", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip().lower()


def limpiar_linea(linea: str) -> str:
    """Quita de una línea del índice los puntos de relleno y los espacios."""
    linea = unicodedata.normalize("NFKC", linea)
    linea = re.sub(r"[.…\s]{3,}", " ", linea)  # '. . . .' y '........'
    return linea.strip()


# Líneas que son decoración del índice, no entradas
CABECERAS = {"índice", "indice", "página", "pagina", "contenido", "páginas"}


# --------------------------------------------------------------------------
# Paso 1: leer el índice
# --------------------------------------------------------------------------

def leer_indice(
    doc: pymupdf.Document,
    paginas_indice: list[int],
) -> list[list[str]]:
    """Devuelve las entradas del índice: una lista de líneas por entrada.

    `paginas_indice` son físicas y empiezan en 1. Son varias porque en dos
    de los tres informes el índice no cabe en una página.

    Todos los índices siguen el mismo patrón: una o varias líneas de
    título, y después una línea que es solo el número de página. Así que
    acumulamos líneas hasta topar con un número. El número lo tiramos.

    Devolvemos las líneas sin unir porque un encabezado sin número de
    página (un "Página" de cabecera de columna, o el nombre de un bloque)
    se acumula con el título que viene detrás. Guardando las líneas sueltas
    podemos luego probar el título entero y también solo su final.
    """
    lineas: list[str] = []
    for pagina in paginas_indice:
        for l in doc[pagina - 1].get_text().split("\n"):
            l = limpiar_linea(l)
            if not l:
                continue
            if re.fullmatch(r"[.…\s\-–—_]+", l):  # solo relleno
                continue
            if normalizar(l) in CABECERAS:
                continue
            lineas.append(l)

    entradas: list[list[str]] = []
    acumulado: list[str] = []

    for l in lineas:
        if re.fullmatch(r"\d{1,4}", l):
            if acumulado:
                entradas.append(acumulado)
                acumulado = []
        else:
            acumulado.append(l)

    if acumulado:
        entradas.append(acumulado)

    return [e for e in entradas if len(" ".join(e)) >= 12]


def variantes_titulo(lineas: list[str]) -> list[str]:
    """Formas en que ese título puede aparecer en el documento.

    De ['Estados financieros', 'Estado consolidado de situación financiera']
    saca el título entero y también solo la última línea, porque la primera
    puede ser un encabezado del índice que en la página no está.

    Van de más específica a menos: la primera que se encuentre, gana.
    """
    completo = " ".join(lineas)
    variantes = [completo]
    for i in range(1, len(lineas)):
        variantes.append(" ".join(lineas[i:]))
    return [v for v in variantes if len(v) >= 12]


# --------------------------------------------------------------------------
# Paso 2: localizar cada título dentro del documento
# --------------------------------------------------------------------------

def buscar_pagina(
    paginas_norm: list[str],
    variantes: list[str],
    desde: int,
    salto_maximo: int = 80,
    longitud_clave: int = 35,
) -> int | None:
    """Primera página (1-indexed) desde `desde` donde aparece el título.

    `paginas_norm` son los textos de todas las páginas ya normalizados: se
    normalizan una sola vez porque con 958 páginas y 300 títulos hacerlo
    dentro del bucle sería cientos de veces más lento.

    Buscamos solo hacia delante porque el documento sigue el orden del
    índice. Eso evita los falsos positivos: "Fondo de comercio" aparece
    docenas de veces en referencias cruzadas, pero su sección empieza una
    sola vez, y después de la anterior.

    `salto_maximo` evita el problema contrario: si un título no está en el
    documento tal como lo escribe el índice, sin ese límite lo
    encontraríamos cientos de páginas más allá, en una mención cualquiera,
    y arrastraríamos el cursor con él.
    """
    hasta = min(len(paginas_norm), desde - 1 + salto_maximo)

    for variante in variantes:
        clave = normalizar(variante)[:longitud_clave]
        if len(clave) < 10:
            continue
        for i in range(desde - 1, hasta):
            if clave in paginas_norm[i]:
                return i + 1
    return None


# --------------------------------------------------------------------------
# Paso 3: montar las secciones
# --------------------------------------------------------------------------

def extraer_secciones(
    ruta: str,
    empresa: str,
    paginas_indice: list[int],
    minimo_caracteres: int = 200,
    maximo_paginas: int = 40,
) -> list[Seccion]:
    """Devuelve las secciones del informe, con su texto y sus páginas.

    `maximo_paginas` corta las secciones que se desbocan: si un título no
    se localiza, la sección anterior se tragaría todo lo que queda del
    documento, y un trozo de 300 páginas no sirve para buscar nada.
    """
    doc = pymupdf.open(ruta)

    try:
        entradas = leer_indice(doc, paginas_indice)
        paginas_norm = [normalizar(doc[i].get_text()) for i in range(len(doc))]

        localizados: list[tuple[str, int]] = []
        cursor = max(paginas_indice) + 1

        for lineas in entradas:
            variantes = variantes_titulo(lineas)
            pagina = buscar_pagina(paginas_norm, variantes, cursor)
            if pagina is not None:
                localizados.append((variantes[-1], pagina))
                cursor = pagina

        secciones: list[Seccion] = []

        for i, (titulo, inicio) in enumerate(localizados):
            if i + 1 < len(localizados):
                fin = max(inicio, localizados[i + 1][1] - 1)
            else:
                fin = len(doc)

            # Una sección larga se parte en trozos, no se trunca: si la
            # cortáramos, las páginas sobrantes no quedarían en ningún
            # trozo y sus datos serían imposibles de encontrar.
            trozos = [
                (p, min(p + maximo_paginas - 1, fin))
                for p in range(inicio, fin + 1, maximo_paginas)
            ]
            parte_de = len(trozos)

            for n, (desde_p, hasta_p) in enumerate(trozos, start=1):
                texto = "\n".join(
                    doc[p].get_text() for p in range(desde_p - 1, hasta_p)
                ).strip()

                if len(texto) < minimo_caracteres:
                    continue

                nombre = titulo if parte_de == 1 else f"{titulo} ({n}/{parte_de})"
                secciones.append(
                    Seccion(
                        empresa=empresa,
                        titulo=nombre,
                        pagina_inicio=desde_p,
                        pagina_fin=hasta_p,
                        texto=texto,
                    )
                )

        return secciones

    finally:
        doc.close()


# --------------------------------------------------------------------------
# Los tres informes y la página donde está su índice impreso
# --------------------------------------------------------------------------

INFORMES = [
    ("data/iberdrola_2025.pdf", "Iberdrola", [14, 15]),
    ("data/santander_2025.pdf", "Santander", [3, 19]),
    ("data/inditex_2025.pdf", "Inditex", [3, 4]),
]


if __name__ == "__main__":
    for ruta, empresa, pags_indice in INFORMES:
        secciones = extraer_secciones(ruta, empresa, pags_indice)
        total = sum(s.n_caracteres for s in secciones)
        medio = total // max(len(secciones), 1)
        print(f"\n{empresa}: {len(secciones)} secciones, "
              f"{total:,} caracteres (media {medio:,})")
        for s in secciones[:4]:
            print("   ", s)