# Ollaya con almacenamiento local

`questions/` es el directorio local para los ficheros JSON de preguntas. La
imagen conserva la imagen GPU oficial y declara `/questions` como su punto de
montaje.

`models/` contiene los modelos descargados por Ollaya. Se monta en
`/home/ollaya/.ollaya/models`, la ruta usada por la imagen oficial. Puede
montarse también en otros contenedores desde el host.

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

Los modelos ya descargados siguen en el volumen Docker `ollaya`. Si quieres
migrarlos al directorio local antes de reemplazar el contenedor, ejecuta:

```shell
docker run --rm -v ollaya:/source \
  --mount type=bind,source="$(pwd)/models",target=/destination \
  alpine sh -c 'cp -a /source/models/. /destination/'
```

Otro contenedor puede usar los mismos modelos montando el directorio local, por
ejemplo en modo de solo lectura:

```shell
docker run --rm --mount type=bind,source="$(pwd)/models",target=/models,readonly alpine ls /models
```

Guarda, por ejemplo, `questions/support.json` y ejecútalo desde el host:

```shell
docker exec -it ollaya ollaya run winnow:e4b --questions /questions/support.json "Hi, I cannot log in since this morning."
```
