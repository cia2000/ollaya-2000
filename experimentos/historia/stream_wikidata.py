#!/usr/bin/env python3
"""Stream historical events from Wikidata to a local Ollaya server."""

import argparse
from collections import Counter, defaultdict
import json
import sys
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
OLLAYA_ENDPOINT = "http://localhost:11435/api/decide"
QUESTIONS = {
    "category": {
        "type": "choice",
        "instructions": "Which category best describes this historical event?",
        "criteria": {
            "conflict": "War, battle, invasion, military action, or armed conflict",
            "politics": "Election, treaty, law, revolution, government, or diplomacy",
            "science": "Scientific, technological, medical, or exploration milestone",
            "disaster": "Natural disaster, accident, epidemic, or humanitarian emergency",
            "culture": "Art, sport, entertainment, religion, or cultural milestone",
            "other": "An event outside the categories above",
        },
    },
    "scope": {
        "type": "choice",
        "instructions": "What was the geographic scope of this historical event?",
        "criteria": {
            "local": "Affected a city, district, or other limited area",
            "national": "Primarily affected one country",
            "regional": "Affected multiple countries in one world region",
            "global": "Had a direct worldwide effect or involved multiple world regions",
        },
    },
    "violence": {
        "type": "score",
        "instructions": "What was the level of violence involved in this event?",
        "criteria": ["None", "Limited", "High", "Massive"],
    },
    "historical_impact": {
        "type": "score",
        "instructions": "What was this event's historical impact?",
        "criteria": ["Minor", "Relevant", "Transformative"],
    },
    "regime_change": {
        "type": "noul",
        "instructions": "Did this event cause or directly involve a change of political regime?",
    },
    "civilian_impact": {
        "type": "noul",
        "instructions": "Did this event primarily affect civilians?",
    },
}


def get_json(url, headers=None, data=None):
    request = Request(url, headers=headers or {}, data=data)
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def get_events(start_year, end_year, limit, offset):
    query = f"""
SELECT ?event ?eventLabel ?eventDescription ?date ?countryLabel WHERE {{
  ?event wdt:P31 wd:Q1190554;
         wdt:P585 ?date;
         rdfs:label ?eventLabel.
  FILTER(YEAR(?date) >= {start_year} && YEAR(?date) <= {end_year})
  FILTER(LANG(?eventLabel) = \"en\")
  OPTIONAL {{
    ?event schema:description ?eventDescription.
    FILTER(LANG(?eventDescription) = \"en\")
  }}
  OPTIONAL {{ ?event wdt:P17 ?country. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language \"en\". }}
}}
ORDER BY ?date ?event
LIMIT {limit}
OFFSET {offset}
"""
    url = f"{WIKIDATA_ENDPOINT}?{urlencode({'query': query, 'format': 'json'})}"
    response = get_json(
        url,
        {"Accept": "application/sparql-results+json", "User-Agent": "ollaya-history-experiment/1.0"},
    )
    return response["results"]["bindings"]


def event_state(event):
    fields = [
        f"Event: {event['eventLabel']['value']}",
        f"Date: {event['date']['value']}",
    ]
    if "eventDescription" in event:
        fields.append(f"Description: {event['eventDescription']['value']}")
    if "countryLabel" in event:
        fields.append(f"Country: {event['countryLabel']['value']}")
    return "\n".join(fields)


def decide(model, event):
    payload = json.dumps({"model": model, "state": event_state(event), "questions": QUESTIONS}).encode()
    started = perf_counter()
    decision = get_json(OLLAYA_ENDPOINT, {"Content-Type": "application/json"}, payload)
    return decision, perf_counter() - started


def choice_summary(answer):
    probability = answer["probabilities"][answer["choice"]]
    return f"{answer['choice']} ({probability:.2%}; confidence {answer['confidence']:.2%})"


def score_summary(answer):
    likely_level = max(answer["probabilities"], key=answer["probabilities"].get)
    likely_probability = answer["probabilities"][likely_level]
    maximum = len(answer["legend"]) - 1
    return (
        f"{answer['score']:.2f}/{maximum} "
        f"({answer['legend'][likely_level]} most likely: {likely_probability:.2%}; "
        f"confidence {answer['confidence']:.2%})"
    )


def pretty_print(event, decision):
    answers = decision["answers"]
    print(f"Event: {event['eventLabel']['value']}")
    print(f"Date:  {event['date']['value'][:10]}")
    if "eventDescription" in event:
        print(f"Description: {event['eventDescription']['value']}")
    print(f"Category: {choice_summary(answers['category'])}")
    print(f"Scope: {choice_summary(answers['scope'])}")
    print(f"Violence: {score_summary(answers['violence'])}")
    print(f"Historical impact: {score_summary(answers['historical_impact'])}")
    print(f"Regime change: {answers['regime_change']['noul']:.2%}")
    print(f"Civilian impact: {answers['civilian_impact']['noul']:.2%}")
    print()


def new_statistics():
    return {
        "dates": [],
        "client_seconds": [],
        "ollaya_seconds": [],
        "eval_seconds": [],
        "load_seconds": [],
        "input_tokens": 0,
        "selected": defaultdict(Counter),
        "probabilities": defaultdict(Counter),
        "scores": defaultdict(list),
        "noul": defaultdict(list),
    }


def record_statistics(statistics, event, decision, client_seconds):
    statistics["dates"].append(event["date"]["value"][:10])
    statistics["client_seconds"].append(client_seconds)
    statistics["ollaya_seconds"].append(decision["total_duration"] / 1_000_000_000)
    statistics["eval_seconds"].append(decision["eval_duration"] / 1_000_000_000)
    statistics["load_seconds"].append(decision["load_duration"] / 1_000_000_000)
    statistics["input_tokens"] += decision["usage"]["input_tokens"]

    for name, question in QUESTIONS.items():
        answer = decision["answers"][name]
        if question["type"] == "choice":
            statistics["selected"][name][answer["choice"]] += 1
            statistics["probabilities"][name].update(answer["probabilities"])
        elif question["type"] == "score":
            likely_level = max(answer["probabilities"], key=answer["probabilities"].get)
            statistics["selected"][name][answer["legend"][likely_level]] += 1
            statistics["probabilities"][name].update(
                {answer["legend"][level]: probability for level, probability in answer["probabilities"].items()}
            )
            statistics["scores"][name].append(answer["score"])
        else:
            probability = answer["noul"]
            statistics["selected"][name]["yes" if probability >= 0.5 else "no"] += 1
            statistics["noul"][name].append(probability)


def print_distribution(output, title, values, counts, probability_totals, total):
    print(f"{title}:", file=output)
    for value in values:
        count = counts[value]
        percentage = count / total
        mean_probability = probability_totals[value] / total
        print(f"  {value}: {count} ({percentage:.1%}); mean probability {mean_probability:.1%}", file=output)


def print_statistics(output, statistics, args, total_seconds):
    total = len(statistics["dates"])
    print("\nOperation summary", file=output)
    print(f"Requested range: {args.start_year}-{args.end_year}", file=output)
    print(f"Observed date range: {min(statistics['dates'])} to {max(statistics['dates'])}", file=output)
    print(f"Events processed: {total}", file=output)
    print(f"Total elapsed time: {total_seconds:.2f} s", file=output)
    print(f"Mean decision time (client): {sum(statistics['client_seconds']) / total:.2f} s", file=output)
    print(f"Mean decision time (Ollaya): {sum(statistics['ollaya_seconds']) / total:.2f} s", file=output)
    print(f"Mean evaluation time: {sum(statistics['eval_seconds']) / total:.2f} s", file=output)
    print(f"Total model-load time: {sum(statistics['load_seconds']):.2f} s", file=output)
    print(f"Input tokens: {statistics['input_tokens']} ({statistics['input_tokens'] / total:.1f} per event)", file=output)

    print("\nClassification distributions", file=output)
    for name, question in QUESTIONS.items():
        title = name.replace("_", " ").title()
        if question["type"] == "choice":
            print_distribution(
                output, title, question["criteria"], statistics["selected"][name], statistics["probabilities"][name], total
            )
        elif question["type"] == "score":
            print_distribution(
                output,
                title,
                question["criteria"],
                statistics["selected"][name],
                statistics["probabilities"][name],
                total,
            )
            print(f"  Mean expected score: {sum(statistics['scores'][name]) / total:.2f}/{len(question['criteria']) - 1}", file=output)
        else:
            yes_count = statistics["selected"][name]["yes"]
            no_count = statistics["selected"][name]["no"]
            mean_probability = sum(statistics["noul"][name]) / total
            print(f"{title}:", file=output)
            print(f"  yes (>=50%): {yes_count} ({yes_count / total:.1%})", file=output)
            print(f"  no (<50%): {no_count} ({no_count / total:.1%})", file=output)
            print(f"  Mean yes probability: {mean_probability:.1%}", file=output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="winnow:e4b")
    parser.add_argument("--start-year", type=int, default=1900)
    parser.add_argument("--end-year", type=int, default=2000)
    parser.add_argument("--limit", type=int, default=20, help="Number of events to stream")
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--pretty", action="store_true", help="Print readable results instead of JSONL")
    args = parser.parse_args()

    if args.limit < 1 or args.page_size < 1 or args.start_year > args.end_year:
        parser.error("use a positive limit and page size, with start-year <= end-year")

    streamed = 0
    offset = 0
    statistics = new_statistics()
    started = perf_counter()
    try:
        while streamed < args.limit:
            events = get_events(args.start_year, args.end_year, min(args.page_size, args.limit - streamed), offset)
            if not events:
                break
            for event in events:
                decision, client_seconds = decide(args.model, event)
                record_statistics(statistics, event, decision, client_seconds)
                if args.pretty:
                    pretty_print(event, decision)
                else:
                    print(
                        json.dumps(
                            {"event": event, "decision": decision, "client_duration_seconds": client_seconds},
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                streamed += 1
            offset += len(events)
    except (HTTPError, URLError, TimeoutError) as error:
        print(f"stream failed: {error}", file=sys.stderr)
        return 1

    if streamed:
        print_statistics(sys.stdout if args.pretty else sys.stderr, statistics, args, perf_counter() - started)
    else:
        print("streamed 0 events", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
