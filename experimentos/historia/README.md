# Experimento de historia

`stream_wikidata.py` obtiene eventos fechados de Wikidata y envía cada evento
a la API local de Ollaya. Cada línea de salida estándar es un objeto JSON que
incluye el registro fuente y la decisión completa, por lo que puede redirigirse a un fichero si es necesario.

He grabado un vídeo en el que hago una demo del experimento: ![Experimento con Ollaya + winow:e4b](https://youtu.be/Ls0mCsddU5A).

## Requisitos

- Python 3. No requiere paquetes adicionales.
- El contenedor Ollaya en ejecución en `http://localhost:11435`.
- El modelo elegido disponible localmente. Por defecto usa `winnow:e4b`.

## Ejecutar

```shell
python3 stream_wikidata.py --limit 10 > resultados.jsonl
```

Para una salida legible en terminal con el nombre, fecha, descripción disponible
y clasificación de cada evento, usa `--pretty`:

```shell
python3 stream_wikidata.py --limit 10 --pretty
```

Al finalizar, el script muestra el rango solicitado y observado, eventos
procesados, duración total, tiempos medios de decisión, carga y evaluación,
tokens de entrada y distribuciones por criterio. En la salida JSONL este
resumen se escribe en la salida de error, de modo que `resultados.jsonl`
contiene solo registros JSON.

El rango temporal predeterminado es 1900-2000. Se puede modificar y elegir un
modelo diferente:

```shell
python3 stream_wikidata.py --model winnow:e4b --start-year 1800 --end-year 1899 --limit 50 > resultados.jsonl
```

El script consulta elementos cuya instancia es `event` en Wikidata, que tienen
la propiedad de fecha `P585` y una etiqueta inglesa. Ollaya clasifica cada
evento por categoría (`conflict`, `politics`, `science`, `disaster`, `culture` u
`other`), alcance geográfico, nivel de violencia, impacto histórico, cambio de
régimen e impacto sobre civiles.

## Interpretación

Este stream produce predicciones, no una medición de eficacia. Para comparar
Ollaya con un LLM frontera hace falta un conjunto de evaluación con una etiqueta
de referencia independiente, un prompt equivalente para ambos modelos y las
métricas definidas antes de ejecutar el experimento, por ejemplo exactitud,
F1 macro, coste y latencia.

Fuentes: [Wikidata Query Service](https://query.wikidata.org/) y
[documentación de la API de Ollaya](https://ollaya.dev/docs/api).
