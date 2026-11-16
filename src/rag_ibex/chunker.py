"""Parte las secciones en trozos del tamaño que necesita la búsqueda.

Una sección puede tener 30.000 caracteres. Para buscar hace falta algo
mucho más pequeño: trozos de unos 1.000, que son los que se convierten en
vectores y se recuperan al responder.
"""

import re
from dataclasses import dataclass

from rag_ibex.extractor import INFORMES, Seccion, extraer_secciones


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


def partir_en_parrafos(texto: str, tamano: int) -> list[str]:
    """Separa el texto en unidades que no conviene romper.

    Baja por tres niveles: primero párrafos (línea en blanco), y lo que
    siga siendo más largo que el límite se parte por líneas, y lo que aún
    lo sea, a lo bruto por caracteres. Sin esta cascada, un "párrafo" que
    en realidad es una página entera sin líneas en blanco se cuela de una
    pieza y dispara el tamaño del trozo.
    """
    unidades: list[str] = []

    for parrafo in re.split(r"\n\s*\n", texto):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        if len(parrafo) <= tamano:
            unidades.append(parrafo)
            continue

        for linea in parrafo.split("\n"):
            linea = linea.strip()
            if not linea:
                continue
            if len(linea) <= tamano:
                unidades.append(linea)
            else:
                for i in range(0, len(linea), tamano):
                    unidades.append(linea[i:i + tamano])

    return unidades


def agrupar(
    parrafos: list[str],
    tamano: int,
    solape: int,
) -> list[str]:
    """Junta párrafos en trozos de ~`tamano` caracteres, con solape.

    El solape repite el final del trozo anterior al principio del
    siguiente: si un dato cae justo en la frontera, así queda entero en
    al menos uno de los dos.
    """
    trozos: list[str] = []
    actual: list[str] = []
    largo = 0

    for p in parrafos:
        # Un párrafo más largo que el límite va solo: partirlo por la mitad
        # rompería una frase, y es mejor un trozo grande que uno sin sentido.
        if len(p) > tamano:
            if actual:
                trozos.append("\n".join(actual))
                actual, largo = [], 0
            trozos.append(p)
            continue

        if largo + len(p) > tamano and actual:
            trozos.append("\n".join(actual))
            # arrancar el siguiente con la cola del anterior
            cola: list[str] = []
            cuenta = 0
            for anterior in reversed(actual):
                if cuenta + len(anterior) > solape:
                    break
                cola.insert(0, anterior)
                cuenta += len(anterior)
            actual = cola
            largo = cuenta

        actual.append(p)
        largo += len(p)

    if actual:
        trozos.append("\n".join(actual))

    return trozos


def trocear(
    seccion: Seccion,
    tamano: int = 1000,
    solape: int = 150,
    minimo: int = 100,
) -> list[Trozo]:
    """Convierte una sección en la lista de sus trozos."""
    parrafos = partir_en_parrafos(seccion.texto, tamano)
    textos = agrupar(parrafos, tamano, solape)

    # Cada trozo empieza por su procedencia. Un trozo que solo contiene
    # números de una tabla no se parece a ninguna pregunta; con la empresa
    # y la sección delante, la búsqueda por significado sí lo encuentra.
    encabezado = f"[{seccion.empresa} — {seccion.titulo}]"

    return [
        Trozo(
            empresa=seccion.empresa,
            seccion=seccion.titulo,
            pagina_inicio=seccion.pagina_inicio,
            pagina_fin=seccion.pagina_fin,
            indice=i,
            texto=f"{encabezado}\n{t}",
        )
        for i, t in enumerate(textos)
        if len(t) >= minimo
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
        largos = [len(t.texto) for t in trozos if t.empresa == empresa]
        print(f"  {empresa:12s} {n:5,} trozos | "
              f"media {sum(largos)//len(largos):5,} chars | "
              f"max {max(largos):6,}")

    print("\nEjemplo:")
    ejemplo = trozos[10]
    print(f"  {ejemplo.fuente}")
    print(f"  {ejemplo.texto[:300]!r}")