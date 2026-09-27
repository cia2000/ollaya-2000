# Experimento de puente y linterna

Resultados, interpretación y límites: [CONCLUSIONES.md](CONCLUSIONES.md).

## El problema

Un grupo debe cruzar un puente de noche con una única linterna. El puente admite
como máximo dos personas a la vez, toda travesía debe llevar la linterna y una
pareja tarda lo mismo que la persona más lenta. El objetivo es llevar a todo el
grupo a la orilla derecha sin exceder un límite de tiempo.

En el caso clásico, las personas tardan 1, 2, 5 y 10 minutos y el límite es 17.
Una secuencia óptima es: cruzan 1 y 2 (2), vuelve 1 (1), cruzan 5 y 10 (10),
vuelve 2 (2), y cruzan 1 y 2 (2). El total es 17 minutos.

Este experimento evalúa decisiones secuenciales sobre el problema clásico del
puente y la linterna. Cada petición a Ollaya recibe el enunciado, el estado de
las dos orillas, la posición de la linterna, el tiempo acumulado, el historial
de decisiones y las acciones legalmente posibles. El controlador aplica la
acción seleccionada y valida el resultado.

El caso predeterminado usa los tiempos y límite del ejemplo clásico.

## Ejecutar

```shell
python3 bridge_torch_experiment.py --delay 0
```

Puedes cambiar los tiempos, el límite y el número máximo de decisiones:

```shell
python3 bridge_torch_experiment.py --times 1,2,7,11 --limit 25 --max-steps 20 --delay 0
```

La salida representa ambas orillas y la linterna en cada turno. El resumen
informa del tiempo óptimo calculado por Dijkstra, resultado, pasos, tiempo
consumido, decisiones forzadas y latencia media. Si se vuelve a un estado ya
alcanzado con igual o mayor coste, termina como `dominated state detected`.

## Benchmark por estado

`benchmark_states.py` evita que una decisión errónea afecte a las siguientes.
Enumera los estados no finales que pueden conducir a una solución dentro del
límite, calcula sus acciones óptimas con Dijkstra y evalúa de forma independiente
la acción elegida por Ollaya. La métrica principal es la exactitud top-1: que la
acción con mayor probabilidad pertenezca al conjunto de acciones óptimas.

```shell
python3 benchmark_states.py
```

Para ver cada estado, etiqueta esperada y predicción:

```shell
python3 benchmark_states.py --verbose
```

## Benchmark con pistas

`benchmark_hints.py` compara el mismo conjunto de estados en cinco condiciones:
sin pista (`baseline`), una lista de comprobación general (`checklist`), una
estrategia explícita para cuatro personas (`strategy`) y un ejemplo resuelto con
tiempos distintos (`few_shot`). `lookahead` añade una tabla de las consecuencias
inmediatas de cada acción legal, sin indicar cuál es óptima. Es aprendizaje en
contexto: las pistas se incluyen en cada petición, pero no se entrenan ni
modifican los pesos del modelo.

```shell
python3 benchmark_hints.py
```

La condición `strategy` codifica conocimiento específico del problema y debe
interpretarse como un techo de rendimiento asistido, no como una comparación
justa con la condición base. Para seleccionar condiciones concretas:

```shell
python3 benchmark_hints.py --conditions baseline,checklist,few_shot
```

## Generalización

`benchmark_generalization.py` evalúa instancias retenidas con tiempos y límites
distintos, pero conserva el mismo enunciado, representación de estado, acciones
legales y métrica top-1. Las instancias predeterminadas son `1,2,7,11:18`,
`1,3,6,8:18` y `1,4,5,9:20`.

```shell
python3 benchmark_generalization.py
```

Para proporcionar otras instancias, usa el formato `TIEMPOS:LIMITE` separado por
punto y coma:

```shell
python3 benchmark_generalization.py --instances '1,2,4,9:16;1,3,5,12:22'
```
