#!/usr/bin/env python3
"""Measure Ollaya's bridge decisions on held-out crossing-time instances."""

import argparse
import sys
from time import perf_counter
from urllib.error import HTTPError, URLError

from benchmark_states import feasible_states, optimal_labels
from bridge_torch_experiment import ask_ollaya, bank, legal_actions, people_for


DEFAULT_INSTANCES = "1,2,7,11:18;1,3,6,8:18;1,4,5,9:20"


def parse_instances(value):
    instances = []
    try:
        for item in value.split(";"):
            times_text, limit_text = item.split(":", 1)
            times = tuple(int(time) for time in times_text.split(","))
            limit = int(limit_text)
            if len(times) < 2 or len(set(times)) != len(times) or any(time < 1 for time in times) or limit < 1:
                raise ValueError
            instances.append((times, limit))
    except ValueError as error:
        raise argparse.ArgumentTypeError("instances use TIMES:LIMIT;TIMES:LIMIT, e.g. 1,2,7,11:18") from error
    return instances


def evaluate_instance(model, times, limit, verbose):
    people = people_for(times)
    states = feasible_states(people, limit)
    correct_count = 0
    probability_sum = 0.0
    confidence_sum = 0.0
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
            decision, duration = ask_ollaya(model, left, torch, elapsed, limit, history, people, actions)
            answer = decision["answers"]["next_action"]
            choice = answer["choice"]
            confidence = answer["confidence"]
            probability = sum(answer["probabilities"].get(label, 0.0) for label in expected)
            input_tokens += decision["usage"]["input_tokens"]
        correct = choice in expected
        correct_count += correct
        probability_sum += probability
        confidence_sum += confidence
        decision_seconds.append(duration)
        if verbose:
            print(
                f"times={','.join(map(str, times))} limit={limit} state={index}: {choice}; "
                f"expected {', '.join(sorted(expected))}; {'correct' if correct else 'incorrect'}"
            )
    total = len(states)
    return {
        "times": times,
        "limit": limit,
        "states": total,
        "correct": correct_count,
        "accuracy": correct_count / total,
        "probability": probability_sum / total,
        "confidence": confidence_sum / total,
        "latency": sum(decision_seconds) / total,
        "tokens": input_tokens,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="winnow:e4b")
    parser.add_argument("--instances", type=parse_instances, default=parse_instances(DEFAULT_INSTANCES))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    started = perf_counter()
    try:
        results = [evaluate_instance(args.model, times, limit, args.verbose) for times, limit in args.instances]
    except (HTTPError, URLError, TimeoutError, KeyError) as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        return 1

    total_states = sum(result["states"] for result in results)
    total_correct = sum(result["correct"] for result in results)
    weighted = lambda field: sum(result[field] * result["states"] for result in results) / total_states
    print("Bridge and torch generalization benchmark")
    print("Times       Limit   States   Top-1 accuracy   Optimal probability   Mean confidence   Mean latency")
    for result in results:
        times = ",".join(map(str, result["times"]))
        print(
            f"{times:<11} {result['limit']:>5} {result['states']:>8}"
            f"      {result['accuracy']:>6.1%} ({result['correct']}/{result['states']})"
            f"        {result['probability']:>6.1%}"
            f"             {result['confidence']:>6.1%}"
            f"          {result['latency']:>5.2f} s"
        )
    print(f"Aggregate: {total_correct}/{total_states} = {total_correct / total_states:.1%} top-1 accuracy")
    print(f"Aggregate optimal probability: {weighted('probability'):.1%}")
    print(f"Aggregate confidence: {weighted('confidence'):.1%}")
    print(f"Aggregate mean latency: {weighted('latency'):.2f} s")
    print(f"Input tokens: {sum(result['tokens'] for result in results)}")
    print(f"Total execution time: {perf_counter() - started:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
