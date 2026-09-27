# Experimento de laberinto

`maze_experiment.py` genera un laberinto perfecto y solicita a Ollaya el
siguiente movimiento en cada turno. El estado enviado incluye el mapa completo,
la posición de `M`, el objetivo `G`, las celdas visitadas y los movimientos
válidos. El laberinto se representa en ASCII: `#` es una pared, `S` el inicio,
`G` la meta, `M` la posición actual y `.` una celda visitada.

## Ejecutar

```shell
python3 maze_experiment.py --complexity 3 --seed 42
```

`--complexity` acepta valores de 1 a 10 y determina un laberinto cuadrado de
`(4 + 2 * complejidad)` celdas por lado. `--seed` hace reproducible el mapa.
Usa `--max-steps` para limitar las decisiones y `--delay 0` para eliminar la
pausa entre fotogramas.

```shell
python3 maze_experiment.py --complexity 5 --seed 2026 --max-steps 200 --delay 0
```

El resumen final compara los pasos usados con la ruta óptima calculada por BFS,
e informa de movimientos inválidos, celdas visitadas y tiempos. En cada
bifurcación se ofrecen a Ollaya exclusivamente los movimientos válidos; en un
corredor sin bifurcación el controlador avanza de forma automática. Si el modelo
repite un estado ya explorado sin descubrir celdas nuevas, el experimento termina
como `cycle detected`. Ollaya no conserva memoria entre peticiones: el
controlador le reenvía el mapa y el historial visible en cada decisión.
