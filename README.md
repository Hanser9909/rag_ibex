# Asistente de informes anuales del IBEX 35

Sistema de recuperación aumentada (RAG) que responde preguntas sobre los informes anuales de **Santander**, **Iberdrola** e **Inditex** (ejercicio 2025), citando la página exacta de la que sale cada dato.

**[Probar la demo](https://huggingface.co/spaces/Hanser9909/rag-ibex)**

```
¿Cuál fue el beneficio atribuido de Santander en 2025?

En 2025, el beneficio atribuido de Banco Santander fue de 14.101 millones
de euros [2][3]. Esta cifra supuso un incremento del 12% respecto a los
12.574 millones registrados en 2024 [2][3].

  [2] Santander, Informe anual 2025 (8/21) (pp. 455-456)
  [3] Santander, Informe anual 2025 (6/21) (p. 346)
```

---

## El problema

La mayoría de demos de RAG usan corpus limpios y homogéneos: documentación técnica, artículos, un conjunto de PDFs generados por la misma herramienta. Este proyecto parte de lo contrario.

Tres informes anuales del mismo índice bursátil, del mismo ejercicio y con el mismo propósito regulatorio, y **ninguno se procesa igual**:

| | Iberdrola | Santander | Inditex |
|---|---|---|---|
| Páginas | 389 | 958 | 465 |
| Caracteres | 922.000 | 3,9 M | 1,8 M |
| Origen del texto | Nativo | Nativo | 92 páginas por OCR |
| Marcadores del PDF | 77% correctos | **0 de 360** | 96% correctos |
| Numeración impresa | Inconsistente | Coincide | Desfase de 2 |

Descubrirlo requirió inspeccionar los documentos antes de escribir una línea de código. Esa inspección es la que evitó rehacer el trabajo a mitad del proyecto.

---

## Cómo funciona

```
PDF → secciones → trozos → vectores → búsqueda → respuesta con citas
```

**1. Extracción** (`extractor.py`) — Lee el índice impreso de cada informe para saber qué secciones existen, y después localiza cada título dentro del documento para saber dónde empieza de verdad. Resultado: 188 secciones.

**2. Troceo** (`chunker.py`) — Parte las secciones en fragmentos de ~1.000 caracteres con 150 de solapamiento, arrastrando la página de la que sale cada uno. Resultado: 7.857 trozos.

**3. Indexación** (`indexador.py`) — Convierte cada trozo en un vector de 768 dimensiones con `multilingual-e5-base`. Resultado: 23 MB de vectores.

**4. Búsqueda** (`indexador.Buscador`) — Similitud coseno contra los 7.857 vectores. Milisegundos.

**5. Generación** (`generador.py`) — Pasa los fragmentos recuperados a un modelo de lenguaje con instrucciones de citar por número y de rechazar lo que no esté en el material.

---

## Decisiones de ingeniería

### El índice impreso en lugar de los marcadores del PDF

Los marcadores de Santander están rotos: sus 360 entradas tienen el destino vacío (`/Dest[null /XYZ null 751 null]`). Verificado con dos librerías independientes y leyendo el objeto PDF en crudo.

La solución no fue escribir una estrategia por documento, sino usar lo único que los tres tienen bien: **el índice impreso en sus páginas**.

### Localizar los títulos en lugar de confiar en sus números

Los números del índice son la numeración impresa, que no coincide con las páginas del archivo. Inditex tiene un desfase constante de 2; Iberdrola no tiene desfase único porque algunas secciones reinician la numeración.

En lugar de modelar cada caso, el extractor usa el índice solo como lista de secciones y **busca cada título dentro del documento**. Avanza siempre hacia delante (el documento sigue el orden del índice) con un límite de salto de 80 páginas, que evita que un título no localizado arrastre al resto.

### Citas a nivel de página

Las primeras versiones citaban el rango de la sección entera: *"pp. 342-381"*. Eso no es una cita, es señalar un capítulo.

`Seccion` guarda el texto como una lista de `(página, texto)` en lugar de concatenado, y el troceo arrastra esa información. Entre el **66% y el 81%** de los trozos acaban en una sola página.

### Contexto en cada trozo

Un fragmento que solo contiene números de una tabla no se parece a ninguna pregunta formulada en lenguaje natural, así que la búsqueda semántica nunca lo encontraría. Cada trozo se prefija con su procedencia:

```
[Iberdrola — Estado consolidado de situación financiera]
Activo intangible
9
22.240
20.255
```

### numpy en lugar de una base de datos vectorial

Con 7.857 vectores, la comparación exhaustiva tarda milisegundos: es una multiplicación de matrices. Un índice aproximado (FAISS, pgvector, Qdrant) empieza a aportar en el orden de cientos de miles de vectores.

Los vectores se guardan en un `.npy` y los metadatos en un `.json`. Añadir una base de datos aquí habría sido complejidad sin beneficio medible.

### Cadena de modelos con respaldo

El modelo de lenguaje más reciente es también el más demandado, y devuelve `503 UNAVAILABLE` con frecuencia. El generador recorre una lista de modelos, con reintentos y espera exponencial en cada uno, y cae al siguiente cuando uno se agota.

En las pruebas, los dos modelos más nuevos fallaron y respondió el más antiguo. **Para un sistema que tiene que funcionar, la disponibilidad pesa más que las capacidades de última generación.**

### Rechazar lo que no está

El prompt obliga a responder `"No encuentro ese dato en los informes."` cuando los fragmentos no contienen la respuesta. Un RAG que inventa es peor que uno que calla: si puede fabricar un dato, no puedes fiarte de ninguno.

---

## Evaluación

Set de 5 preguntas con respuesta y página verificadas manualmente. Tres niveles de test:

| Test | Qué comprueba | Resultado |
|---|---|---|
| `test_cobertura` | Que alguna sección incluye la página de la respuesta | 5/5 |
| `test_trozos` | Que la cifra concreta está en un trozo recuperable | 5/5 |
| `evaluar` | Que el trozo correcto sale entre los 5 primeros (recall@5) | 100% |

**Con una reserva importante:** cinco preguntas no bastan para medir mejoras. Las puntuaciones de similitud entre el acierto y los siguientes resultados difieren en milésimas (0.890 / 0.890 / 0.890), así que el orden es frágil y cualquier cambio puede alterarlo sin que signifique nada.

Ampliar el set a 25-30 preguntas es el siguiente paso antes de cualquier optimización.

---

## Ejecutar el proyecto

```bash
uv sync
```

Coloca los tres informes en `data/` como `iberdrola_2025.pdf`, `santander_2025.pdf` e `inditex_2025.pdf`. Son públicos, en la web de relación con inversores de cada empresa.

```bash
# Construir el índice (descarga el modelo de embeddings la primera vez)
uv run python -m rag_ibex.indexador

# Medir la búsqueda
uv run python -m rag_ibex.evaluar

# Preguntar desde la terminal
uv run python -m rag_ibex.generador "¿Cuántos empleados tenía Santander?"

# Interfaz web
uv run python app.py
```

Requiere una clave de API en `GEMINI_API_KEY`.

---

## Limitaciones conocidas

- **El set de evaluación tiene 5 preguntas.** Suficiente para detectar que algo está roto, insuficiente para medir mejoras.
- **Las secciones de Santander están mal etiquetadas.** Su índice general solo lista capítulos de alto nivel, así que el 83% de sus trozos acaban con un título genérico (`Informe anual 2025 (6/21)`). La página sí es correcta.
- **92 páginas de Inditex vienen de OCR** y contienen erratas de reconocimiento (`confldence`, `Limlted`). Un error en una cifra sería un fallo silencioso.
- **Las tablas pierden su estructura.** Se extraen como texto plano, en columnas de números sin encabezado cercano. El extractor de tablas de PyMuPDF los corrompe más (`22.240` → `22240` + `.`), así que el texto plano es el mal menor.
- **Sin búsqueda híbrida ni reranking.** Son las mejoras evidentes, pero no tiene sentido implementarlas hasta poder medir si funcionan.
- **Un solo proveedor de modelos.** La cadena de respaldo cubre la caída de un modelo, no la del proveedor entero.

---

## Stack

Python 3.12 - PyMuPDF - sentence-transformers - numpy - Gradio - Gemini API - uv
