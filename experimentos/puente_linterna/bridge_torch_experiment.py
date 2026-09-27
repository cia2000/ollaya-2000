#!/usr/bin/env python3
"""Run a local Ollaya model on the bridge and torch planning problem."""

import argparse
import heapq
import json
import sys
from itertools import combinations
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OLLAYA_ENDPOINT = "http://localhost:11435/api/decide"
PROBLEM = (
    "A group must cross a bridge at night with one torch. At most two people cross at once, "
    "the torch must travel with every crossing, and a pair takes the slower person's time. "
    "Move everybody to the right bank before the time limit."
)


def parse_times(value):
    try:
        times = [int(item) for item in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("times must be comma-separated positive integers") from error
    if len(times) < 2 or any(time < 1 for time in times) or len(set(times)) != len(times):
        raise argparse.ArgumentTypeError("provide at least two distinct positive times")
    return times


def people_for(times):
    return {chr(ord("A") + index): crossing_time for index, crossing_time in enumerate(times)}


def action_label(people, direction):
    return f"{'_'.join(person.lower() for person in people)}_to_{direction}"


def legal_actions(left, torch, people):
    source = left if torch == "left" else set(people) - set(left)
    direction = "right" if torch == "left" else "left"
    actions = []
    for group_size in (1, 2):
        for group in combinations(sorted(source), group_size):
            actions.append(
                {
                    "label": action_label(group, direction),
                    "people": group,
                    "direction": direction,
                    "cost": max(people[person] for person in group),
                }
            )
    return actions


def apply_action(left, action):
    group = set(action["people"])
    if action["direction"] == "right":
        return frozenset(set(left) - group), "right"
    return frozenset(set(left) | group), "left"


def optimal_time(people):
    start = frozenset(people)
    queue = [(0, 0, start, "left")]
    best = {(start, "left"): 0}
    sequence = 0
    while queue:
        elapsed, _, left, torch = heapq.heappop(queue)
        if not left:
            return elapsed
        if elapsed != best[(left, torch)]:
            continue
        for action in legal_actions(left, torch, people):
            next_left, next_torch = apply_action(left, action)
            next_elapsed = elapsed + action["cost"]
            state = next_left, next_torch
            if next_elapsed < best.get(state, float("inf")):
                best[state] = next_elapsed
                sequence += 1
                heapq.heappush(queue, (next_elapsed, sequence, next_left, next_torch))
    raise RuntimeError("no solution exists")


def describe_action(action):
    group = "+".join(action["people"])
    return f"{group} crosses to the {action['direction']} bank; cost {action['cost']} minutes"


def bank(people, members):
    return ", ".join(f"{person}({people[person]})" for person in sorted(members)) or "empty"


def ask_ollaya(model, left, torch, elapsed, limit, history, people, actions, advice=None):
    right = set(people) - set(left)
    state = {
        "problem": PROBLEM,
        "state": {
            "left_bank": bank(people, left),
            "right_bank": bank(people, right),
            "torch": torch,
            "elapsed_minutes": elapsed,
            "remaining_minutes": limit - elapsed,
        },
        "history": history,
        "instruction": "Choose one legal action that can lead to a solution before the time limit.",
    }
    if advice:
        state["planning_advice"] = advice
    question = {
        "next_action": {
            "type": "choice",
            "instructions": "Which legal crossing should happen next?",
            "criteria": {action["label"]: describe_action(action) for action in actions},
        }
    }
    payload = json.dumps({"model": model, "state": state, "questions": question}).encode()
    request = Request(OLLAYA_ENDPOINT, data=payload, headers={"Content-Type": "application/json"})
    started = perf_counter()
    with urlopen(request, timeout=120) as response:
        decision = json.load(response)
    return decision, perf_counter() - started


def print_state(people, left, torch, elapsed, limit, step, last_action):
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")
    right = set(people) - set(left)
    torch_marker = " [torch]" if torch == "left" else ""
    print(f"Bridge and torch | step {step} | elapsed {elapsed}/{limit} minutes")
    print(f"LEFT : {bank(people, left)}{torch_marker}")
    print("                 ========= bridge =========")
    torch_marker = " [torch]" if torch == "right" else ""
    print(f"RIGHT: {bank(people, right)}{torch_marker}")
    if last_action:
        print(f"Last action: {last_action}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="winnow:e4b")
    parser.add_argument("--times", type=parse_times, default=[1, 2, 5, 10])
    parser.add_argument("--limit", type=int, default=17, help="Maximum allowed crossing time")
    parser.add_argument("--max-steps", type=int, default=24)
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()
    if args.limit < 1 or args.max_steps < 1 or args.delay < 0:
        parser.error("limit and max-steps must be positive, and delay must not be negative")

    people = people_for(args.times)
    left = frozenset(people)
    torch = "left"
    elapsed = 0
    history = []
    decision_seconds = []
    forced_actions = 0
    best_elapsed = {}
    last_action = None
    outcome = "step limit reached"
    optimum = optimal_time(people)
    started = perf_counter()

    try:
        for step in range(args.max_steps + 1):
            print_state(people, left, torch, elapsed, args.limit, step, last_action)
            if not left:
                outcome = "goal reached"
                break
            if elapsed > args.limit:
                outcome = "time limit exceeded"
                break
            state = left, torch
            if elapsed >= best_elapsed.get(state, float("inf")):
                outcome = "dominated state detected"
                break
            best_elapsed[state] = elapsed

            actions = legal_actions(left, torch, people)
            if len(actions) == 1:
                action = actions[0]
                forced_actions += 1
                confidence = None
            else:
                decision, duration = ask_ollaya(args.model, left, torch, elapsed, args.limit, history, people, actions)
                decision_seconds.append(duration)
                answer = decision["answers"]["next_action"]
                action = next(item for item in actions if item["label"] == answer["choice"])
                confidence = answer["confidence"]

            left, torch = apply_action(left, action)
            elapsed += action["cost"]
            last_action = describe_action(action)
            if confidence is not None:
                last_action += f" (confidence {confidence:.1%})"
            history.append({"action": describe_action(action), "elapsed_minutes": elapsed})
            if args.delay:
                sleep(args.delay)
    except (HTTPError, URLError, TimeoutError, KeyError, StopIteration) as error:
        print(f"experiment failed: {error}", file=sys.stderr)
        return 1

    if not left:
        outcome = "goal reached"
    total_seconds = perf_counter() - started
    print("Experiment summary")
    print(f"People and times: {bank(people, people)}")
    print(f"Time limit: {args.limit} minutes")
    print(f"Optimal time: {optimum} minutes")
    print(f"Outcome: {outcome}")
    print(f"Steps: {len(history)}")
    print(f"Crossing time used: {elapsed} minutes")
    print(f"Time efficiency: {optimum / elapsed:.1%}" if not left and elapsed else "Time efficiency: n/a")
    print(f"Forced actions: {forced_actions}")
    print(f"Total execution time: {total_seconds:.2f} s")
    if decision_seconds:
        print(f"Mean decision time: {sum(decision_seconds) / len(decision_seconds):.2f} s")
    return 0 if not left and elapsed <= args.limit else 2


if __name__ == "__main__":
    raise SystemExit(main())
