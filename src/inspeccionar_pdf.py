import sys
from collections import Counter

import pymupdf

ruta = sys.argv[1]
doc = pymupdf.open(ruta)

print(f"=== {ruta}")
print(f"Paginas: {len(doc)}")
print(f"Metadatos: {doc.metadata.get('producer')} | {doc.metadata.get('creator')}")
print(f"Cifrado: {doc.is_encrypted}")

# 1. Texto extraible?
sin_texto = 0
chars_por_pagina = []
for p in doc:
    t = p.get_text().strip()
    chars_por_pagina.append(len(t))
    if len(t) < 50:
        sin_texto += 1
print(f"\n--- TEXTO")
print(f"Paginas con <50 chars (posible imagen): {sin_texto} de {len(doc)}")
print(f"Chars por pagina: min={min(chars_por_pagina)} media={sum(chars_por_pagina)//len(doc)} max={max(chars_por_pagina)}")
print(f"Total chars: {sum(chars_por_pagina):,}")

# 2. Bookmarks / indice
toc = doc.get_toc()
print(f"\n--- INDICE (bookmarks)")
print(f"Entradas: {len(toc)}")
for nivel, titulo, pag in toc[:25]:
    print(f"  {'  '*(nivel-1)}[{nivel}] p{pag}: {titulo[:70]}")

# 3. Encabezados y pies repetidos
primeras = Counter()
ultimas = Counter()
for p in doc:
    lineas = [l.strip() for l in p.get_text().split("\n") if l.strip()]
    if lineas:
        primeras[lineas[0][:60]] += 1
        ultimas[lineas[-1][:60]] += 1
print(f"\n--- PRIMERA LINEA mas repetida")
for txt, n in primeras.most_common(6):
    print(f"  {n:4d}x  {txt!r}")
print(f"--- ULTIMA LINEA mas repetida")
for txt, n in ultimas.most_common(6):
    print(f"  {n:4d}x  {txt!r}")

# 4. Tamanos de fuente (para detectar titulos)
tam = Counter()
for p in list(doc)[:60]:
    d = p.get_text("dict")
    for b in d.get("blocks", []):
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                tam[round(s["size"], 1)] += len(s["text"])
print(f"\n--- TAMANOS DE FUENTE (primeras 60 pags, por volumen de texto)")
for t, n in tam.most_common(10):
    print(f"  {t:6.1f}pt  {n:7d} chars")

# 5. Tablas detectadas
print(f"\n--- TABLAS (muestra de paginas)")
for n_pag in [40, 100, 180, 250, 320]:
    if n_pag < len(doc):
        tablas = doc[n_pag].find_tables()
        print(f"  p{n_pag}: {len(tablas.tables)} tablas detectadas")

doc.close()