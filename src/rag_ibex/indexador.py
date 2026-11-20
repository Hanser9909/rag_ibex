"""Convierte los trozos en vectores y los guarda en disco.

Un embedding es una lista de números que representa el significado de un
texto. Dos textos que hablan de lo mismo tienen vectores parecidos, aunque
no compartan ni una palabra. Eso es lo que permite buscar por significado
en vez de por coincidencia literal.

Con 7.857 trozos no hace falta una base de datos vectorial: comparar una
pregunta contra todos ellos con numpy tarda milisegundos. Guardamos los
vectores en un .npy y los metadatos en un .json.
"""

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from rag_ibex.chunker import Trozo, trocear_todo

MODELO = "intfloat/multilingual-e5-base"
CARPETA = Path("indice")
REPO_INDICE = "Hanser9909/rag-ibex-indice"

# E5 necesita estos prefijos: fue entrenado con ellos y sin ellos
# los resultados empeoran de forma silenciosa.
PREFIJO_DOCUMENTO = "passage: "
PREFIJO_PREGUNTA = "query: "


def construir_indice(
    trozos: list[Trozo] | None = None,
    modelo_nombre: str = MODELO,
    carpeta: Path = CARPETA,
    batch_size: int = 32,
) -> None:
    """Calcula los vectores de todos los trozos y los guarda."""
    from sentence_transformers import SentenceTransformer

    if trozos is None:
        print("Troceando los informes...")
        trozos = trocear_todo()
    print(f"{len(trozos):,} trozos")

    print(f"Cargando {modelo_nombre}...")
    modelo = SentenceTransformer(modelo_nombre)

    textos = [PREFIJO_DOCUMENTO + t.texto for t in trozos]

    print("Calculando vectores (esto tarda)...")
    vectores = modelo.encode(
        textos,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,  # así el parecido es un producto escalar
        convert_to_numpy=True,
    ).astype(np.float32)

    carpeta.mkdir(parents=True, exist_ok=True)
    np.save(carpeta / "vectores.npy", vectores)

    with open(carpeta / "trozos.json", "w", encoding="utf-8") as f:
        json.dump([asdict(t) for t in trozos], f, ensure_ascii=False)

    with open(carpeta / "config.json", "w", encoding="utf-8") as f:
        json.dump({"modelo": modelo_nombre, "dimensiones": vectores.shape[1]}, f)

    peso = vectores.nbytes / 1024 / 1024
    print(f"\nGuardado en {carpeta}/")
    print(f"  vectores.npy  {vectores.shape}  ({peso:.1f} MB)")
    print(f"  trozos.json   {len(trozos):,} trozos")


class Buscador:
    """Busca los trozos más parecidos a una pregunta."""

    def __init__(self, carpeta: Path = CARPETA):
        from sentence_transformers import SentenceTransformer

        # En local usamos el índice construido; en un despliegue esa
        # carpeta no existe, así que se descarga del dataset y queda en
        # caché para los siguientes arranques.
        if not (carpeta / "vectores.npy").exists():
            from huggingface_hub import snapshot_download

            carpeta = Path(
                snapshot_download(repo_id=REPO_INDICE, repo_type="dataset")
            )

        self.vectores = np.load(carpeta / "vectores.npy")

        with open(carpeta / "trozos.json", encoding="utf-8") as f:
            self.trozos = [Trozo(**d) for d in json.load(f)]

        with open(carpeta / "config.json", encoding="utf-8") as f:
            config = json.load(f)

        self.modelo = SentenceTransformer(config["modelo"])

    def buscar(self, pregunta: str, k: int = 5) -> list[tuple[float, Trozo]]:
        """Los k trozos más parecidos, con su puntuación."""
        v = self.modelo.encode(
            PREFIJO_PREGUNTA + pregunta,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

        # Como todos los vectores están normalizados, el producto escalar
        # ES la similitud coseno. Una multiplicación y ya está.
        puntuaciones = self.vectores @ v

        mejores = np.argsort(-puntuaciones)[:k]
        return [(float(puntuaciones[i]), self.trozos[i]) for i in mejores]


if __name__ == "__main__":
    construir_indice()