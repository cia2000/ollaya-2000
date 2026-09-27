#!/usr/bin/env python3
"""Compare Ollaya's bridge decisions with general and in-context planning hints."""

import argparse
import sys
from time import perf_counter
from urllib.error import HTTPError, URLError

from benchmark_states import feasible_states, optimal_labels
from bridge_torch_experiment import apply_action, ask_ollaya, bank, legal_actions, people_for, parse_times


HINTS = {
    "baseline": None,
    "checklist": (
        "Plan before choosing: compare the cost of every legal action, account for the torch return, "
        "and reject an action that recreates a previous physical state with more elapsed time. "
        "Choose an action that preserves a feasible route within the remaining time."
    ),
    "strategy": (
        "For four people ordered from fastest A to slowest D, a useful strategy when the two slowest "
        "must cross together is: send A+B right, return A, send C+D right, return B, then send A+B right. "
        "Apply this only when it matches the current state and time limit."
    ),
    "few_shot": (
        "Worked example on a different instance: A=1, B=2, C=7 and D=11 with a 25-minute limit. "
        "An 18-minute solution is A+B right (2), A left (1), C+D right (11), B left (2), A+B right (2). "
        "Use the example to reason about the current instance; do not copy actions unless they fit the state."
    ),
    "lookahead": None,
}


def lookahead_advice(left, elapsed, limit, people, actions):
    lines = [
        "Planning worksheet. Each line gives an immediate legal consequence only; it does not identify the best action."
    ]
    for action in actions:
        next_left, next_torch = apply_action(left, action)
        next_elapsed = elapsed + action["cost"]
        next_right = set(people) - set(next_left)
        lines.append(
            f"{action['label']}: left=[{bank(people, next_left)}], right=[{bank(people, next_right)}], "
            f"torch={next_torch}, elapsed={next_elapsed}, remaining={limit - next_elapsed}."
        )
    return "\n".join(lines)


def evaluate(condition, model, people, limit, states, verbose):
    correct_count = 0
    confidence_sum = 0.0
    probability_sum = 0.0
    decision_seconds = []
    input_tokens = 0
    for index, (left, torch, elapsed, history, _) in enumerate(states, start=1):
        actions = legal_actions(left, torch, people)
        expected = optimal_labels(left, torch, people)
        if len(actions) == 1:
            choice = actions[0]["label"]
            confidence = probability = 1.0
            duration = 0.0
        else:
            advice = lookahead_advice(left, elapsed, limit, people, actions) if condition == "lookahead" else HINTS[condition]
            decision, duration = ask_ollaya(
                model, left, torch, elapsed, limit, history, people, actions, advice
            )
            answer = decision["answers"]["next_action"]
            choice = answer["choice"]
            confidence = answer["confidence"]
            probability = sum(answer["probabilities"].get(label, 0.0) for label in expected)
            input_tokens += decision["usage"]["input_tokens"]
        correct = choice in expected
        correct_count += correct
        confidence_sum += confidence
        probability_sum += probability
        decision_seconds.append(duration)
        if verbose:
            print(f"{condition} state {index}: {choice}; expected {', '.join(sorted(expected))}; {'correct' if correct else 'incorrect'}")

    total = len(states)
    return {
        "condition": condition,
        "accuracy": correct_count / total,
        "correct": correct_count,
        "mean_probability": probability_sum / total,
        "mean_confidence": confidence_sum / total,
        "mean_seconds": sum(decision_seconds) / total,
        "input_tokens": input_tokens,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="winnow:e4b")
    parser.add_argument("--times", type=parse_times, default=[1, 2, 5, 10])
    parser.add_argument("--limit", type=int, default=17)
    parser.add_argument("--conditions", default="baseline,checklist,strategy,few_shot,lookahead")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    conditions = args.conditions.split(",")
    unknown = set(conditions) - set(HINTS)
    if args.limit < 1 or unknown:
        parser.error(f"use a positive limit and conditions from: {', '.join(HINTS)}")

    people = people_for(args.times)
    states = feasible_states(people, args.limit)
    if not states:
        print("No feasible non-goal states for the requested times and limit.", file=sys.stderr)
        return 2

    started = perf_counter()
    try:
        results = [evaluate(condition, args.model, people, args.limit, states, args.verbose) for condition in conditions]
    except (HTTPError, URLError, TimeoutError, KeyError) as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        return 1

    print("Bridge and torch hint benchmark")
    print(f"People and times: {bank(people, people)}")
    print(f"Time limit: {args.limit} minutes; states evaluated: {len(states)}")
    print("Condition       Top-1 accuracy   Optimal probability   Mean confidence   Mean latency   Input tokens")
    for result in results:
        print(
            f"{result['condition']:<15} {result['accuracy']:>6.1%} ({result['correct']}/{len(states)})"
            f"        {result['mean_probability']:>6.1%}"
            f"             {result['mean_confidence']:>6.1%}"
            f"          {result['mean_seconds']:>5.2f} s"
            f"       {result['input_tokens']}"
        )
    print(f"Total execution time: {perf_counter() - started:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
