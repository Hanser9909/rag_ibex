"""Responde preguntas usando los trozos recuperados.

Este es el paso que convierte el buscador en un sistema que responde: se
recuperan los trozos relevantes, se le pasan a un modelo de lenguaje y
este redacta la respuesta citando de dónde sale cada dato.

Necesita una clave de API en la variable de entorno GEMINI_API_KEY.
Para usar otro proveedor, cambia solo la función `llamar_modelo`.
"""

import os
import re
from dataclasses import dataclass

from rag_ibex.chunker import Trozo
from rag_ibex.indexador import Buscador

MODELOS = ["gemini-2.5-flash", "gemini-3.7-flash", "gemini-3.5-flash"]

INSTRUCCIONES = """\
Eres un asistente que responde preguntas sobre informes anuales de \
empresas del IBEX 35.

Reglas:
- Responde SOLO con la información de los fragmentos que te doy.
- Cita la fuente de cada dato con su número entre corchetes: [1], [2].
- Si los fragmentos no contienen la respuesta, di exactamente: "No \
encuentro ese dato en los informes." No deduzcas ni estimes.
- Si encuentras cifras contradictorias, dilo y cita ambas.
- Da la cifra con sus unidades y el año al que corresponde.
- Responde en dos o tres frases. Sin preámbulos.\
"""


@dataclass
class Respuesta:
    pregunta: str
    texto: str
    fuentes: list[Trozo]

    @property
    def fuentes_citadas(self) -> list[int]:
        """Números de fuente que el modelo citó de verdad."""
        return sorted({int(n) for n in re.findall(r"\[(\d+)\]", self.texto)})

    def formatear(self) -> str:
        lineas = [self.texto, ""]
        for n in self.fuentes_citadas:
            if 1 <= n <= len(self.fuentes):
                lineas.append(f"  [{n}] {self.fuentes[n - 1].fuente}")
        return "\n".join(lineas)


def construir_prompt(pregunta: str, trozos: list[Trozo]) -> str:
    """Monta el texto que se le manda al modelo."""
    bloques = []
    for i, t in enumerate(trozos, start=1):
        bloques.append(f"[{i}] Fuente: {t.fuente}\n{t.texto}")

    return (
        f"{INSTRUCCIONES}\n\n"
        f"FRAGMENTOS:\n\n" + "\n\n---\n\n".join(bloques) + "\n\n"
        f"PREGUNTA: {pregunta}"
    )


def _llamar_uno(
    prompt: str,
    modelo: str,
    intentos: int = 2,
) -> str:
    """llama a un modelo en concreto, reintentando ante fallos temporales.

    La espera se dobla cada vez (2s, 4s): si todos los clientes reintentaran al segundo, un servidor sat;urado nunca se recuperaría.
    """
    import time

    from google import genai
    from google.genai import types

    clave = os.environ.get("GEMINI_API_KEY")
    if not clave:
        raise RuntimeError(
            "Falta GEMINI_API_KEY. En PowerShell: $env:GEMINI_API_KEY = 'tu-clave'"
        )

    cliente = genai.Client(api_key=clave, http_options=types.HttpOptions(timeout=60_000),)

    for intento in range(1, intentos + 1):
        try:
            respuesta = cliente.models.generate_content(
                model=modelo,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return respuesta.text.strip()
        except Exception as e:
            codigo = getattr(e, "code", None)
            mensaje = str(e).lower()
            temporal = (
                codigo in (429, 500, 502, 503, 504)
                or "disconnect" in mensaje
                or "timeout" in mensaje
                or "connection" in mensaje
            )
            if not temporal or intento == intentos:
                raise
            espera = 2 ** intento
            print(f"   ({modelo}: reintento {intento} en {espera}s)", flush=True)
            time.sleep(espera)

    raise RuntimeError("No debería llegar aquí")



def llamar_modelo(prompt: str, modelos: list[str] = MODELOS) -> str:
    """Prueba los modelos en orden hasta que uno responda.

    Depender de un solo modelo es frágil: el más reciente suele ser el más
    demandado y devuelve 503 con facilidad. Si falla, se cae al siguiente.
    """
    ultimo_error: Exception | None = None

    for modelo in modelos:
        try:
            return _llamar_uno(prompt, modelo)
        except Exception as e:
            print(f"   ({modelo} agotado: {type(e).__name__})", flush=True)
            ultimo_error = e

    raise RuntimeError(
        f"Ningún modelo respondió. Último error: {ultimo_error}"
    ) from ultimo_error

class Asistente:
    """Junta la búsqueda y la generación."""

    def __init__(self, k: int = 5):
        self.buscador = Buscador()
        self.k = k

    def preguntar(self, pregunta: str) -> Respuesta:
        resultados = self.buscador.buscar(pregunta, k=self.k)
        trozos = [t for _, t in resultados]
        texto = llamar_modelo(construir_prompt(pregunta, trozos))
        return Respuesta(pregunta=pregunta, texto=texto, fuentes=trozos)


if __name__ == "__main__":
    import sys

    asistente = Asistente()

    preguntas = sys.argv[1:] or [
        "¿Cuál fue el beneficio atribuido de Santander en 2025?",
        "¿Cuántos empleados tenía Santander a cierre de 2025?",
        "¿Cuál es el presupuesto de marketing de Iberdrola para 2027?",
    ]

    for p in preguntas:
        print(f"\n{'=' * 70}\n{p}\n{'=' * 70}")
        print(asistente.preguntar(p).formatear())