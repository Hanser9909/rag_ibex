"""Parte las secciones en trozos del tamaño que necesita la búsqueda.

Una sección puede tener 30.000 caracteres. Para buscar hace falta algo
mucho más pequeño: trozos de unos 1.000, que son los que se convierten en
vectores y se recuperan al responder.

Cada trozo arrastra la página o páginas de las que sale, no el rango de su
sección entera: así la cita de una respuesta es "p. 346" y no
"pp. 342-381", que no sirve para comprobar nada.
"""

import re
from dataclasses import dataclass

from rag_ibex.extractor import INFORMES, Seccion, extraer_secciones

# Una unidad de texto con la página de la que sale
Unidad = tuple[int, str]


@dataclass
class Trozo:
    """Un fragmento de texto listo para indexar, con su procedencia."""

    empresa: str
    seccion: str
    pagina_inicio: int
    pagina_fin: int
    indice: int          # posición dentro de su sección
    texto: str

    @property
    def fuente(self) -> str:
        """Cómo se cita este trozo en una respuesta."""
        if self.pagina_inicio == self.pagina_fin:
            paginas = f"p. {self.pagina_inicio}"
        else:
            paginas = f"pp. {self.pagina_inicio}-{self.pagina_fin}"
        return f"{self.empresa}, {self.seccion} ({paginas})"

    def __repr__(self) -> str:
        return f"Trozo({self.fuente}, #{self.indice}, {len(self.texto)} chars)"


def partir_en_unidades(seccion: Seccion, tamano: int) -> list[Unidad]:
    """Trocea la sección en unidades pequeñas, cada una con su página.

    Baja por tres niveles: primero párrafos (línea en blanco), lo que siga
    siendo más largo que el límite se parte por líneas, y lo que aún lo
    sea, por caracteres. Sin esta cascada, un "párrafo" que en realidad es
    una página entera sin líneas en blanco se cuela de una pieza y dispara
    el tamaño del trozo.
    """
    unidades: list[Unidad] = []

    for n_pagina, texto_pagina in seccion.paginas:
        for parrafo in re.split(r"\n\s*\n", texto_pagina):
            parrafo = parrafo.strip()
            if not parrafo:
                continue
            if len(parrafo) <= tamano:
                unidades.append((n_pagina, parrafo))
                continue

            for linea in parrafo.split("\n"):
                linea = linea.strip()
                if not linea:
                    continue
                if len(linea) <= tamano:
                    unidades.append((n_pagina, linea))
                else:
                    for i in range(0, len(linea), tamano):
                        unidades.append((n_pagina, linea[i:i + tamano]))

    return unidades


def agrupar(
    unidades: list[Unidad],
    tamano: int,
    solape: int,
) -> list[tuple[int, int, str]]:
    """Junta unidades en trozos de ~`tamano` caracteres, con solape.

    Devuelve (primera página, última página, texto) por trozo.

    El solape repite el final del trozo anterior al principio del
    siguiente: si un dato cae justo en la frontera, así queda entero en al
    menos uno de los dos.
    """
    trozos: list[tuple[int, int, str]] = []
    actual: list[Unidad] = []
    largo = 0

    def cerrar(grupo: list[Unidad]) -> None:
        if grupo:
            paginas = [p for p, _ in grupo]
            trozos.append((min(paginas), max(paginas), "\n".join(t for _, t in grupo)))

    for pagina, texto in unidades:
        if largo + len(texto) > tamano and actual:
            cerrar(actual)
            # arrancar el siguiente con la cola del anterior
            cola: list[Unidad] = []
            cuenta = 0
            for anterior in reversed(actual):
                if cuenta + len(anterior[1]) > solape:
                    break
                cola.insert(0, anterior)
                cuenta += len(anterior[1])
            actual = cola
            largo = cuenta

        actual.append((pagina, texto))
        largo += len(texto)

    cerrar(actual)
    return trozos


def trocear(
    seccion: Seccion,
    tamano: int = 1000,
    solape: int = 150,
    minimo: int = 100,
) -> list[Trozo]:
    """Convierte una sección en la lista de sus trozos."""
    unidades = partir_en_unidades(seccion, tamano)
    agrupados = agrupar(unidades, tamano, solape)

    # Cada trozo empieza por su procedencia. Un trozo que solo contiene
    # números de una tabla no se parece a ninguna pregunta; con la empresa
    # y la sección delante, la búsqueda por significado sí lo encuentra.
    encabezado = f"[{seccion.empresa} — {seccion.titulo}]"

    return [
        Trozo(
            empresa=seccion.empresa,
            seccion=seccion.titulo,
            pagina_inicio=desde,
            pagina_fin=hasta,
            indice=i,
            texto=f"{encabezado}\n{texto}",
        )
        for i, (desde, hasta, texto) in enumerate(agrupados)
        if len(texto) >= minimo
    ]


def trocear_todo(tamano: int = 1000, solape: int = 150) -> list[Trozo]:
    """Todos los trozos de los tres informes."""
    trozos: list[Trozo] = []
    for ruta, empresa, pags_indice in INFORMES:
        for seccion in extraer_secciones(ruta, empresa, pags_indice):
            trozos.extend(trocear(seccion, tamano, solape))
    return trozos


if __name__ == "__main__":
    from collections import Counter

    trozos = trocear_todo()
    print(f"Trozos totales: {len(trozos):,}")

    por_empresa = Counter(t.empresa for t in trozos)
    for empresa, n in por_empresa.items():
        propios = [t for t in trozos if t.empresa == empresa]
        largos = [len(t.texto) for t in propios]
        una_pagina = sum(1 for t in propios if t.pagina_inicio == t.pagina_fin)
        print(f"  {empresa:12s} {n:5,} trozos | "
              f"media {sum(largos)//len(largos):5,} chars | "
              f"{una_pagina * 100 // n}% en una sola página")

    print("\nEjemplo de cita:")
    for t in trozos[:3]:
        print(f"  {t.fuente}")