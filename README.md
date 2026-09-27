# Ollaya con almacenamiento local

Este repositorio ejecuta la imagen CUDA oficial de Ollaya con los modelos y las
preguntas en directorios locales. Ollaya evalúa un estado (texto, correo,
ticket o JSON) frente a preguntas tipadas y devuelve respuestas con
probabilidades calibradas en una sola pasada. No es un modelo de generación de
texto.

## Recursos oficiales

- [Sitio web de Ollaya](https://ollaya.dev/)
- [Instalación y requisitos de Docker/GPU](https://ollaya.dev/download)
- [Guía de inicio rápido](https://ollaya.dev/docs/quickstart)
- [Documentación general](https://ollaya.dev/docs)
- [Referencia de la CLI](https://ollaya.dev/docs/cli)
- [Referencia de la API](https://ollaya.dev/docs/api)
- [Catálogo y comparativa de modelos](https://ollaya.dev/search)
- [Modelfile: preguntas integradas en un modelo](https://ollaya.dev/docs/modelfile)
- [Repositorio oficial](https://github.com/ollaya-dev/ollaya)

La imagen `:cuda` requiere NVIDIA Container Toolkit y un controlador con CUDA
13 (R580 o posterior). Para controladores CUDA 12 (R525 a R575), sustituye la
imagen base del `Dockerfile` por `ghcr.io/ollaya-dev/ollaya:cuda12`.

## Directorios locales

- `questions/`: ficheros JSON de preguntas proporcionados al modelo.
- `models/`: modelos descargados. Se monta en
  `/home/ollaya/.ollaya/models`, la ruta configurada por la imagen oficial, y
  puede compartirse con otros contenedores mediante un bind mount.

Ambos directorios están excluidos de Git. `questions.example.json` sí se
versiona para proporcionar un caso de prueba reproducible.

## Crear y ejecutar el contenedor

Construye la imagen desde este directorio:

```shell
docker build -t ollaya-local-questions .
```
Crea y ejecuta un contenedor a partir de la imagen:

```shell
docker stop ollaya
docker rm ollaya
docker run -d --name ollaya --gpus=all -p 11435:11435 \
  --mount type=bind,source="$(pwd)/questions",target=/questions \
  --mount type=bind,source="$(pwd)/models",target=/home/ollaya/.ollaya/models \
  ollaya-local-questions
```

El servicio queda disponible en `http://localhost:11435`. El puerto se publica
en todas las interfaces del host; no lo expongas a una red no confiable. Para
proteger una instancia accesible remotamente, configura `OLLAYA_API_KEY` y
sitúala tras un proxy TLS. Consulta la [sección de seguridad de la
API](https://ollaya.dev/docs/api#security).

Comprueba que el servicio responde:

```shell
curl http://localhost:11435/
```

## Modelos y decisiones

Descarga un modelo con `pull` o deja que `run` lo descargue en el primer uso.
`laya` es un router ligero para inglés y más de 100 idiomas; el catálogo
oficial permite elegir otros modelos según precisión, latencia, idioma y tipo
de tarea.

```shell
docker exec -it ollaya ollaya pull laya
docker exec -it ollaya ollaya list
docker exec -it ollaya ollaya ps
```

El modelo recibe un estado y un conjunto de preguntas. Los tres tipos de
pregunta son `choice` (una opción), `score` (nivel esperado) y `noul`
(probabilidad de que una afirmación sea cierta). La [referencia de
preguntas](https://ollaya.dev/docs/api#questions) define su esquema completo.

Para probar la configuración, crea el fichero local de preguntas a partir del
ejemplo incluido:

```shell
cp questions.example.json questions/support.json
```

Ejecuta una decisión desde el host. `run` descargará `winnow:e4b` si aún no
existe; consulta su tamaño en el [catálogo de modelos](https://ollaya.dev/library/winnow).

```shell
docker exec -it ollaya ollaya run winnow:e4b --questions /questions/support.json "Hi, I cannot log in since this morning."
```

También puedes consumir la API nativa con `POST /api/decide` o la API
compatible con TypeSafe bajo `/v1/*`:

```shell
curl http://localhost:11435/api/decide -d '{
  "model": "laya",
  "state": "Hi, I cannot log in since this morning.",
  "questions": {
    "angry": {"type": "noul", "instructions": "Is the customer angry?"}
  }
}'
```

## Compartir los modelos

Otro contenedor puede usar los mismos modelos montando el directorio local, por
ejemplo en modo de solo lectura:

```shell
docker run --rm --mount type=bind,source="$(pwd)/models",target=/models,readonly alpine ls /models
```
