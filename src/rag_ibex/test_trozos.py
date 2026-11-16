"""Comprueba que la respuesta de cada pregunta cae dentro de algún trozo.

Más exigente que test_cobertura: no basta con que la página esté incluida,
la cifra concreta tiene que estar en un trozo recuperable.
"""

import sys

from rag_ibex.chunker import trocear_todo

# (empresa, texto que debe aparecer, descripción)
RESPUESTAS = [
    ("Santander", "14.101", "Beneficio atribuido 2025"),
    ("Inditex", "1,75", "Dividendo por acción"),
    ("Iberdrola", "8.389", "Fondo de comercio 31/12/2025"),
    ("Santander", "198.403", "Empleados a cierre de 2025"),
    ("Iberdrola", "44 GW", "Capacidad instalada renovable"),
]


def main() -> int:
    trozos = trocear_todo()
    print(f"{len(trozos):,} trozos\n")

    fallos = 0
    for empresa, aguja, descripcion in RESPUESTAS:
        encontrados = [
            t for t in trozos
            if t.empresa == empresa and aguja in t.texto
        ]
        if encontrados:
            t = encontrados[0]
            print(f"  OK    {descripcion}: {aguja!r} en {len(encontrados)} trozo(s)")
            print(f"        primero: {t.fuente[:75]}")
        else:
            fallos += 1
            print(f"  FALLO {descripcion}: {aguja!r} no aparece en ningún trozo de {empresa}")

    print(f"\n{len(RESPUESTAS) - fallos} de {len(RESPUESTAS)} respuestas recuperables")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())