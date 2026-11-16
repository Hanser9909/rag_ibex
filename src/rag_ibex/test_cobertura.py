"""Comprueba que las secciones extraídas cubren las respuestas conocidas.

Cada pregunta del set de evaluación tiene su respuesta en una página
concreta. Si ninguna sección cubre esa página, el sistema no podrá
responderla por mucho que mejoremos la búsqueda después.
"""

import sys

from rag_ibex.extractor import INFORMES, extraer_secciones

PREGUNTAS = [
    ("Santander", 346, "Beneficio atribuido 2025: 14.101 M€"),
    ("Inditex", 92, "Dividendo por acción: 1,75 €"),
    ("Iberdrola", 16, "Fondo de comercio 31/12/2025: 8.389 M€"),
    ("Santander", 235, "Empleados a cierre de 2025: 198.403"),
    ("Iberdrola", 296, "Capacidad instalada: más de 44 GW"),
]


def main() -> int:
    por_empresa = {}
    for ruta, empresa, pags_indice in INFORMES:
        por_empresa[empresa] = extraer_secciones(ruta, empresa, pags_indice)

    fallos = 0
    for empresa, pagina, descripcion in PREGUNTAS:
        cubren = [
            s for s in por_empresa[empresa]
            if s.pagina_inicio <= pagina <= s.pagina_fin
        ]
        if cubren:
            s = cubren[0]
            print(f"  OK    {empresa} p{pagina}: {s.titulo[:45]!r} "
                  f"(pp.{s.pagina_inicio}-{s.pagina_fin}, {s.n_caracteres:,} chars)")
        else:
            fallos += 1
            print(f"  FALLO {empresa} p{pagina}: ninguna sección la cubre — {descripcion}")

    print(f"\n{len(PREGUNTAS) - fallos} de {len(PREGUNTAS)} páginas cubiertas")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())