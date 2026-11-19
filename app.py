"""Interfaz web del asistente sobre informes anuales del IBEX 35."""

import os

import gradio as gr

from rag_ibex.generador import Asistente

TITULO = "Preguntas sobre informes anuales del IBEX 35"

DESCRIPCION = """\
Asistente que responde preguntas sobre los informes anuales de **Santander**, \
**Iberdrola** e **Inditex** (ejercicio 2025), citando la página de la que sale \
cada dato.

Construido sobre 1.812 páginas de PDF, troceadas en 7.857 fragmentos indexados \
con embeddings multilingües. Si el dato no está en los informes, lo dice en \
lugar de inventárselo.
"""

EJEMPLOS = [
    "¿Cuál fue el beneficio atribuido de Santander en 2025?",
    "¿Cuántos empleados tenía Santander a cierre de 2025?",
    "¿Cuánto fondo de comercio tenía Iberdrola a 31 de diciembre de 2025?",
    "¿Qué capacidad instalada renovable tiene Iberdrola?",
    "¿Cuál fue el dividendo por acción de Inditex?",
    "¿Cuál es el presupuesto de marketing de Iberdrola para 2027?",
]

_asistente: Asistente | None = None


def obtener_asistente(k: int) -> Asistente:
    """Carga el asistente una sola vez y reutiliza el modelo de embeddings."""
    global _asistente
    if _asistente is None:
        _asistente = Asistente(k=k)
    _asistente.k = k
    return _asistente


def responder(pregunta: str, k: int, progress=gr.Progress()) -> tuple[str, str]:
    if not pregunta.strip():
        return "Escribe una pregunta.", ""

    progress(0.2, desc="Buscando fragmentos...")
    try:
        respuesta = obtener_asistente(int(k)).preguntar(pregunta)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"**Error:** {type(e).__name__} — {e}", ""

    partes = [respuesta.texto, "", "---", "", "**Fuentes citadas**", ""]
    for n in respuesta.fuentes_citadas:
        if 1 <= n <= len(respuesta.fuentes):
            partes.append(f"- `[{n}]` {respuesta.fuentes[n - 1].fuente}")
    if not respuesta.fuentes_citadas:
        partes.append("_El modelo no citó ninguna fuente._")

    # Panel de auditoría: todo lo que se le pasó al modelo, citado o no
    recuperados = []
    for i, t in enumerate(respuesta.fuentes, start=1):
        marca = "**(citado)**" if i in respuesta.fuentes_citadas else ""
        cuerpo = t.texto.split("\n", 1)[-1]  # sin el encabezado de contexto
        recuperados.append(
            f"### [{i}] {t.fuente} {marca}\n\n```\n{cuerpo[:900]}\n```"
        )

    return "\n".join(partes), "\n\n".join(recuperados)


with gr.Blocks(title=TITULO, theme=gr.themes.Soft()) as demo:
    gr.Markdown(f"# {TITULO}\n\n{DESCRIPCION}")

    with gr.Row():
        pregunta = gr.Textbox(
            label="Pregunta",
            placeholder="¿Cuál fue el beneficio de Santander en 2025?",
            lines=2,
            scale=4,
        )
        k = gr.Slider(
            label="Fragmentos a recuperar",
            minimum=3,
            maximum=10,
            value=5,
            step=1,
            scale=1,
        )

    boton = gr.Button("Preguntar", variant="primary")
    salida = gr.Markdown(label="Respuesta")

    with gr.Accordion("Ver los fragmentos recuperados", open=False):
        gr.Markdown(
            "_Todo lo que se le pasó al modelo para responder. "
            "Sirve para comprobar si la respuesta se apoya en algo real._"
        )
        fragmentos = gr.Markdown()

    gr.Examples(examples=EJEMPLOS, inputs=pregunta)

    boton.click(responder, inputs=[pregunta, k], outputs=[salida, fragmentos])
    pregunta.submit(responder, inputs=[pregunta, k], outputs=[salida, fragmentos])


if __name__ == "__main__":
    if not os.environ.get("GEMINI_API_KEY"):
        print("AVISO: falta GEMINI_API_KEY; las respuestas fallarán.")
    demo.launch()