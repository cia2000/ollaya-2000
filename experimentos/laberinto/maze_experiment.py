#!/usr/bin/env python3
"""Run a local Ollaya model through a generated maze."""

import argparse
import json
import random
import sys
from collections import deque
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OLLAYA_ENDPOINT = "http://localhost:11435/api/decide"
DIRECTIONS = {
    "north": (-1, 0, "south"),
    "south": (1, 0, "north"),
    "west": (0, -1, "east"),
    "east": (0, 1, "west"),
}
MOVE_CRITERIA = {
    "north": "Move M one cell north",
    "south": "Move M one cell south",
    "west": "Move M one cell west",
    "east": "Move M one cell east",
}


def generate_maze(height, width, seed):
    rng = random.Random(seed)
    walls = {(row, column): set(DIRECTIONS) for row in range(height) for column in range(width)}
    start = (0, 0)
    visited = {start}
    stack = [start]

    while stack:
        row, column = stack[-1]
        candidates = []
        for direction, (row_delta, column_delta, _) in DIRECTIONS.items():
            neighbor = row + row_delta, column + column_delta
            if 0 <= neighbor[0] < height and 0 <= neighbor[1] < width and neighbor not in visited:
                candidates.append((direction, neighbor))
        if not candidates:
            stack.pop()
            continue
        direction, neighbor = rng.choice(candidates)
        walls[(row, column)].remove(direction)
        walls[neighbor].remove(DIRECTIONS[direction][2])
        visited.add(neighbor)
        stack.append(neighbor)
    return walls


def render_maze(walls, height, width, position, goal, route):
    canvas = [["#" for _ in range(width * 2 + 1)] for _ in range(height * 2 + 1)]
    for row in range(height):
        for column in range(width):
            canvas[row * 2 + 1][column * 2 + 1] = "." if (row, column) in route else " "
            for direction, (row_delta, column_delta, _) in DIRECTIONS.items():
                if direction not in walls[(row, column)]:
                    canvas[row * 2 + 1 + row_delta][column * 2 + 1 + column_delta] = " "
    canvas[1][1] = "S"
    canvas[goal[0] * 2 + 1][goal[1] * 2 + 1] = "G"
    canvas[position[0] * 2 + 1][position[1] * 2 + 1] = "M"
    return "\n".join("".join(line) for line in canvas)


def valid_moves(walls, position):
    return [direction for direction in DIRECTIONS if direction not in walls[position]]


def shortest_path_length(walls, start, goal):
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        position, distance = queue.popleft()
        if position == goal:
            return distance
        for direction in valid_moves(walls, position):
            row_delta, column_delta, _ = DIRECTIONS[direction]
            neighbor = position[0] + row_delta, position[1] + column_delta
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, distance + 1))
    raise RuntimeError("generated maze has no path to the goal")


def ask_ollaya(model, walls, maze_map, position, goal, route, moves):
    state = {
        "legend": "# wall, blank open cell, S start, G goal, M current model position, . visited cell",
        "maze": maze_map,
        "position": {"row": position[0], "column": position[1]},
        "goal": {"row": goal[0], "column": goal[1]},
        "valid_moves": valid_moves(walls, position),
        "visited_cells": len(route),
    }
    question = {
        "next_move": {
            "type": "choice",
            "instructions": "Choose the next move for M. Reach G in as few moves as possible.",
            "criteria": {move: MOVE_CRITERIA[move] for move in moves},
        }
    }
    payload = json.dumps({"model": model, "state": state, "questions": question}).encode()
    request = Request(OLLAYA_ENDPOINT, data=payload, headers={"Content-Type": "application/json"})
    started = perf_counter()
    with urlopen(request, timeout=120) as response:
        decision = json.load(response)
    return decision, perf_counter() - started


def print_frame(walls, height, width, position, goal, route, step, choice, valid):
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")
    print(f"Maze {width}x{height} | step {step} | valid moves: {', '.join(valid)}")
    if choice:
        print(f"Ollaya chose: {choice}")
    print(render_maze(walls, height, width, position, goal, route))
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="winnow:e4b")
    parser.add_argument("--complexity", type=int, default=3, help="Integer from 1 to 10; controls maze dimensions")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-steps", type=int, help="Defaults to four times the number of cells")
    parser.add_argument("--delay", type=float, default=0.15, help="Seconds to pause after each rendered move")
    args = parser.parse_args()

    if not 1 <= args.complexity <= 10:
        parser.error("complexity must be between 1 and 10")
    if args.delay < 0:
        parser.error("delay must not be negative")

    height = width = 4 + args.complexity * 2
    walls = generate_maze(height, width, args.seed)
    start = position = (0, 0)
    goal = (height - 1, width - 1)
    optimal_steps = shortest_path_length(walls, start, goal)
    max_steps = args.max_steps or height * width * 4
    route = {position}
    invalid_moves = 0
    forced_moves = 0
    decision_seconds = []
    seen_states = set()
    started = perf_counter()
    last_choice = None
    outcome = "step limit reached"

    try:
        for step in range(max_steps + 1):
            valid = valid_moves(walls, position)
            print_frame(walls, height, width, position, goal, route, step, last_choice, valid)
            if position == goal:
                outcome = "goal reached"
                break
            signature = position, frozenset(route)
            if signature in seen_states:
                outcome = "cycle detected"
                break
            seen_states.add(signature)
            maze = render_maze(walls, height, width, position, goal, route)
            if len(valid) == 1:
                last_choice = f"{valid[0]} (forced)"
                forced_moves += 1
            else:
                decision, elapsed = ask_ollaya(args.model, walls, maze, position, goal, route, valid)
                decision_seconds.append(elapsed)
                last_choice = decision["answers"]["next_move"]["choice"]
            move = last_choice.split()[0]
            if move not in valid:
                invalid_moves += 1
            else:
                row_delta, column_delta, _ = DIRECTIONS[move]
                position = position[0] + row_delta, position[1] + column_delta
                route.add(position)
            if args.delay:
                sleep(args.delay)
        else:
            step = max_steps
    except (HTTPError, URLError, TimeoutError, KeyError) as error:
        print(f"experiment failed: {error}", file=sys.stderr)
        return 1

    if position == goal:
        outcome = "goal reached"
    reached_goal = outcome == "goal reached"
    total_seconds = perf_counter() - started
    print("Experiment summary")
    print(f"Seed: {args.seed}")
    print(f"Complexity: {args.complexity} ({width}x{height})")
    print(f"Outcome: {outcome}")
    print(f"Steps: {step} (optimal: {optimal_steps})")
    if reached_goal and step:
        print(f"Path efficiency: {optimal_steps / step:.1%}")
    else:
        print("Path efficiency: n/a (goal not reached)")
    print(f"Invalid moves: {invalid_moves}")
    print(f"Forced corridor moves: {forced_moves}")
    print(f"Unique cells visited: {len(route)}/{width * height}")
    print(f"Total time: {total_seconds:.2f} s")
    if decision_seconds:
        print(f"Mean decision time: {sum(decision_seconds) / len(decision_seconds):.2f} s")
    return 0 if reached_goal else 2


if __name__ == "__main__":
    raise SystemExit(main())
