#!/usr/bin/env python3
"""Evaluate Ollaya's next-action choices on independently labelled bridge states."""

import argparse
import heapq
import sys
from time import perf_counter
from urllib.error import HTTPError, URLError

from bridge_torch_experiment import (
    action_label,
    apply_action,
    ask_ollaya,
    bank,
    legal_actions,
    people_for,
    parse_times,
)


def shortest_remaining(left, torch, people):
    queue = [(0, 0, left, torch)]
    best = {(left, torch): 0}
    sequence = 0
    while queue:
        cost, _, current_left, current_torch = heapq.heappop(queue)
        if not current_left:
            return cost
        if cost != best[(current_left, current_torch)]:
            continue
        for action in legal_actions(current_left, current_torch, people):
            next_left, next_torch = apply_action(current_left, action)
            next_cost = cost + action["cost"]
            state = next_left, next_torch
            if next_cost < best.get(state, float("inf")):
                best[state] = next_cost
                sequence += 1
                heapq.heappush(queue, (next_cost, sequence, next_left, next_torch))
    raise RuntimeError("state cannot reach the goal")


def feasible_states(people, limit):
    start = frozenset(people)
    queue = [(0, 0, start, "left")]
    best = {(start, "left"): 0}
    histories = {(start, "left"): []}
    sequence = 0
    while queue:
        elapsed, _, left, torch = heapq.heappop(queue)
        state = left, torch
        if elapsed != best[state]:
            continue
        for action in legal_actions(left, torch, people):
            next_left, next_torch = apply_action(left, action)
            next_elapsed = elapsed + action["cost"]
            next_state = next_left, next_torch
            if next_elapsed <= limit and next_elapsed < best.get(next_state, float("inf")):
                best[next_state] = next_elapsed
                histories[next_state] = histories[state] + [
                    {"action": action_label(action["people"], action["direction"]), "elapsed_minutes": next_elapsed}
                ]
                sequence += 1
                heapq.heappush(queue, (next_elapsed, sequence, next_left, next_torch))

    states = []
    for (left, torch), elapsed in best.items():
        if not left:
            continue
        remaining = shortest_remaining(left, torch, people)
        if elapsed + remaining <= limit:
            states.append((left, torch, elapsed, histories[(left, torch)], remaining))
    return sorted(states, key=lambda item: (item[2], len(item[0]), item[1]))


def optimal_labels(left, torch, people):
    remaining = shortest_remaining(left, torch, people)
    labels = set()
    for action in legal_actions(left, torch, people):
        next_left, next_torch = apply_action(left, action)
        if action["cost"] + shortest_remaining(next_left, next_torch, people) == remaining:
            labels.add(action["label"])
    return labels


def print_case(index, people, left, torch, elapsed, limit, expected, answer, correct):
    right = set(people) - set(left)
    probability = answer["probabilities"][answer["choice"]]
    print(f"State {index}")
    print(f"  Left: {bank(people, left)}")
    print(f"  Right: {bank(people, right)}")
    print(f"  Torch: {torch}; elapsed: {elapsed}/{limit} minutes")
    print(f"  Optimal action(s): {', '.join(sorted(expected))}")
    print(f"  Ollaya: {answer['choice']} ({probability:.1%}; confidence {answer['confidence']:.1%})")
    print(f"  Result: {'correct' if correct else 'incorrect'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="winnow:e4b")
    parser.add_argument("--times", type=parse_times, default=[1, 2, 5, 10])
    parser.add_argument("--limit", type=int, default=17)
    parser.add_argument("--max-states", type=int, help="Evaluate at most this many states")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.limit < 1 or args.max_states is not None and args.max_states < 1:
        parser.error("limit and max-states must be positive")

    people = people_for(args.times)
    states = feasible_states(people, args.limit)
    if args.max_states:
        states = states[: args.max_states]
    if not states:
        print("No feasible non-goal states for the requested times and limit.", file=sys.stderr)
        return 2

    started = perf_counter()
    correct_count = 0
    confidence_sum = 0.0
    probability_sum = 0.0
    decision_seconds = []
    input_tokens = 0
    try:
        for index, (left, torch, elapsed, history, _) in enumerate(states, start=1):
            actions = legal_actions(left, torch, people)
            expected = optimal_labels(left, torch, people)
            if len(actions) == 1:
                choice = actions[0]["label"]
                answer = {"choice": choice, "confidence": 1.0, "probabilities": {choice: 1.0}}
                duration = 0.0
            else:
                decision, duration = ask_ollaya(args.model, left, torch, elapsed, args.limit, history, people, actions)
                answer = decision["answers"]["next_action"]
                input_tokens += decision["usage"]["input_tokens"]
            correct = answer["choice"] in expected
            correct_count += correct
            confidence_sum += answer["confidence"]
            probability_sum += sum(answer["probabilities"].get(label, 0.0) for label in expected)
            decision_seconds.append(duration)
            if args.verbose:
                print_case(index, people, left, torch, elapsed, args.limit, expected, answer, correct)
    except (HTTPError, URLError, TimeoutError, KeyError) as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        return 1

    total = len(states)
    print("Bridge and torch state benchmark")
    print(f"People and times: {bank(people, people)}")
    print(f"Time limit: {args.limit} minutes")
    print(f"States evaluated: {total}")
    print(f"Top-1 optimal-action accuracy: {correct_count / total:.1%} ({correct_count}/{total})")
    print(f"Mean probability on optimal actions: {probability_sum / total:.1%}")
    print(f"Mean confidence: {confidence_sum / total:.1%}")
    print(f"Mean decision time: {sum(decision_seconds) / total:.2f} s")
    print(f"Input tokens: {input_tokens} ({input_tokens / total:.1f} per state)")
    print(f"Total execution time: {perf_counter() - started:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
