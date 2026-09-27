# Conclusiones del experimento de puente y linterna

## Objetivo

Evaluar si `winnow:e4b` puede seleccionar el siguiente movimiento óptimo en un
problema secuencial cuando recibe el enunciado, el estado actual, el historial
de decisiones y únicamente las acciones legales.

El problema clásico tiene cuatro personas con tiempos 1, 2, 5 y 10 minutos. Hay
una sola linterna, pueden cruzar una o dos personas y cada cruce cuesta el tiempo
de la persona más lenta. El límite es 17 minutos y la solución óptima también
cuesta 17 minutos.

## Diseño

El controlador genera y aplica las transiciones. Ollaya no conserva memoria
entre peticiones: en cada turno recibe de nuevo el problema, las dos orillas, la
posición de la linterna, el tiempo transcurrido, el historial y las acciones
posibles.

`benchmark_states.py` evita que un error temprano afecte a los turnos
posteriores. Enumera los estados no finales desde los que todavía se puede
resolver el problema dentro del límite y usa Dijkstra para etiquetar el conjunto
de acciones óptimas. En el caso clásico hay siete estados de evaluación.

La exactitud top-1 cuenta como acierto si la acción con mayor probabilidad de
Ollaya pertenece al conjunto de acciones óptimas para ese estado.

## Resultado base

Ejecutado con `winnow:e4b`:

| Métrica | Resultado |
|---|---:|
| Estados evaluados | 7 |
| Exactitud top-1 | 57.1% (4/7) |
| Probabilidad media en acciones óptimas | 41.3% |
| Confianza media | 44.1% |
| Latencia media por decisión | 0.11 s |
| Tokens de entrada medios por estado | 373.7 |

En la ejecución cerrada del problema, el modelo eligió primero `A+B -> right` y
después `A -> left`, ambos movimientos compatibles con una solución óptima. En
el tercer turno eligió `A -> right` en vez de `C+D -> right`, recreando una
configuración física ya visitada con mayor coste. El controlador lo detectó como
`dominated state detected` y terminó la partida.

## Pistas evaluadas

`benchmark_hints.py` evaluó las mismas siete instancias con información adicional
en el contexto. Ninguna pista reveló la acción óptima del estado evaluado ni
incluyó el resultado de Dijkstra.

| Condición | Contenido adicional | Top-1 | Probabilidad óptima media | Confianza media |
|---|---|---:|---:|---:|
| `baseline` | Ninguno | 57.1% | 41.3% | 44.1% |
| `checklist` | Lista general para comparar costes y evitar volver a estados peores | 57.1% | 45.6% | 47.2% |
| `strategy` | Estrategia conocida para trasladar a las dos personas más lentas | 57.1% | 43.8% | 49.0% |
| `few_shot` | Ejemplo resuelto con tiempos distintos | 57.1% | 39.2% | 46.4% |
| `lookahead` | Consecuencia inmediata, coste y tiempo restante de cada acción legal | 42.9% | 43.8% | 60.5% |

Los errores top-1 se repitieron en las cuatro primeras condiciones: el modelo
priorizó cruces rápidos de `A` o `B` donde la acción óptima era cruzar `C+D`.
La condición `lookahead` empeoró la exactitud y aumentó la confianza, un caso de
sobreconfianza inducida por contexto adicional.

## Generalización a tiempos retenidos

`benchmark_generalization.py` mantuvo el enunciado, formato de estado y métrica,
pero cambió los tiempos de cruce y el límite. Cada instancia se etiquetó de nuevo
con Dijkstra.

| Tiempos | Límite | Estados | Top-1 | Probabilidad óptima media |
|---|---:|---:|---:|---:|
| 1, 2, 7, 11 | 18 | 7 | 57.1% (4/7) | 43.1% |
| 1, 3, 6, 8 | 18 | 7 | 57.1% (4/7) | 39.0% |
| 1, 4, 5, 9 | 20 | 13 | 76.9% (10/13) | 46.7% |
| Agregado | - | 27 | 66.7% (18/27) | 43.8% |

La exactitud no es uniforme: dos variantes mantuvieron el 57.1% del caso
clásico y una alcanzó 76.9%. Esto muestra sensibilidad a los tiempos, pero no
demuestra todavía una generalización amplia: todas las pruebas pertenecen a la
misma familia de cuatro personas y usan la misma representación.

## Interpretación

No se puede concluir que el modelo use exclusivamente conocimiento interno. Las
pistas modificaron probabilidades y confianza, por ejemplo de 41.3% a 45.6% de
probabilidad media sobre acciones óptimas con `checklist`. El contexto se procesa,
pero no cambió los `argmax` que causan los tres errores principales.

La evidencia actual indica que:

- `winnow:e4b` puede clasificar correctamente varias decisiones individuales del
  problema, pero no planifica de forma fiable una secuencia óptima.
- Las instrucciones, una estrategia textual y un ejemplo en contexto no elevaron
  la exactitud top-1 en este conjunto pequeño.
- Una tabla de consecuencias inmediatas no sustituyó la planificación a varios
  pasos y produjo mayor confianza sin mayor corrección.
- La mejora agregada en las instancias retenidas no es consistente entre ellas;
  se debe informar por instancia, no solo como una media global.
- Una partida cerrada no es una métrica suficiente: un único error puede impedir
  acabar el problema. El benchmark independiente por estado aísla mejor la
  calidad de cada decisión.

## Límites

- Solo se evaluó una instancia de cuatro personas y siete estados; no permite
  generalizar a todos los problemas de planificación.
- Las siete instancias están relacionadas entre sí y proceden del mismo problema.
- El modelo puede haber visto el acertijo clásico durante su entrenamiento.
- Las pistas se evaluaron una vez por estado; el modelo es determinista para una
  misma petición, pero todavía faltan variantes de formulación y problemas
  retenidos.
- La condición `strategy` contiene conocimiento específico del dominio. Es una
  medida de rendimiento asistido, no una comparación de capacidad desde cero.

## Siguiente paso

Realizar una prueba contrafactual y de generalización:

1. Generar varias instancias retenidas cambiando tiempos y límites.
2. Mantener el enunciado y las acciones legales, cambiando solo una variable
   crítica por petición: tiempos, posición de la linterna o tiempo restante.
3. Comprobar que la acción y sus probabilidades cambian en la dirección predicha
   por Dijkstra.
4. Ejecutar el mismo conjunto, prompt y métricas contra un LLM frontera.
5. Informar exactitud top-1, masa de probabilidad óptima, calibración, latencia,
   tokens y tasa de resolución en partidas cerradas.

## Reproducción

```shell
python3 benchmark_states.py --verbose
python3 benchmark_hints.py
python3 bridge_torch_experiment.py --delay 0
```
