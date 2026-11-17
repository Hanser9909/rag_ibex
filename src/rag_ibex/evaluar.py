"""Mide si la búsqueda encuentra los trozos que contienen las respuestas.

La métrica es recall@k: de las preguntas del set, en cuántas aparece un
trozo con la respuesta entre los k primeros resultados.

Es la medida que importa: si el trozo correcto no sale entre los que
recuperamos, el modelo de lenguaje no tiene con qué responder, por bueno
que sea.
"""

import sys

from rag_ibex.indexador import Buscador

# (pregunta, empresa, texto que debe contener el trozo correcto)
PREGUNTAS = [
    ("¿Cuál fue el beneficio atribuido de Santander en 2025?",
     "Santander", "14.101"),
    ("¿Cuánto fue el dividendo por acción de Inditex?",
     "Inditex", "1,75"),
    ("¿Cuánto fondo de comercio tenía Iberdrola a 31 de diciembre de 2025?",
     "Iberdrola", "8.389"),
    ("¿Cuántos empleados tenía Santander a cierre de 2025?",
     "Santander", "198.403"),
    ("¿Qué capacidad instalada renovable tiene Iberdrola?",
     "Iberdrola", "44 GW"),
]


def evaluar(k: int = 5, verboso: bool = True) -> float:
    buscador = Buscador()
    aciertos = 0

    for pregunta, empresa, aguja in PREGUNTAS:
        resultados = buscador.buscar(pregunta, k=k)

        posicion = None
        for i, (_, trozo) in enumerate(resultados, start=1):
            if trozo.empresa == empresa and aguja in trozo.texto:
                posicion = i
                break

        if posicion:
            aciertos += 1
            print(f"  OK    (puesto {posicion}) {pregunta[:52]}")
        else:
            print(f"  FALLO            {pregunta[:52]}")

        if verboso:
            for i, (score, t) in enumerate(resultados[:3], start=1):
                marca = "<--" if (t.empresa == empresa and aguja in t.texto) else "   "
                print(f"        {i}. {score:.3f} {marca} {t.fuente[:62]}")

    recall = aciertos / len(PREGUNTAS)
    print(f"\nrecall@{k} = {recall:.0%}  ({aciertos} de {len(PREGUNTAS)})")
    return recall


if __name__ == "__main__":
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    evaluar(k)