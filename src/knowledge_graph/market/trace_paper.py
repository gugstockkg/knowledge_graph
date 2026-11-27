"""Symbolic core of Ding et al. (arXiv:2603.12500), §§3.3–3.5 and Algorithm 1."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class Edge:
    source: str
    relation: str
    target: str
    published: str
    valid_from: str
    valid_to: str | None = None

    def visible(self, as_of):
        return (
            self.published <= as_of
            and self.valid_from <= as_of
            and (self.valid_to is None or as_of <= self.valid_to)
        )


@dataclass(frozen=True)
class Rule:
    body: tuple[str, ...]
    label: str
    support: int
    confidence: float


class TemporalGraph:
    def __init__(self, edges, text_sources):
        self.edges = defaultdict(list)
        for edge in edges:
            self.edges[edge.source].append(edge)
        self.text_sources = frozenset(text_sources)

    def expand(self, start, path, as_of):
        visited = {start, *(edge.target for edge in path)}
        head = path[-1].target if path else start
        for edge in self.edges[head]:
            if edge.target not in visited and edge.visible(as_of):
                yield (*path, edge)

    def degree(self, node, as_of):
        return sum(edge.visible(as_of) for edge in self.edges[node])


def body(path):
    return tuple(edge.relation for edge in path)


def mine_rules(graph, observations, train_end, *, min_support, threshold=0.60):
    """Count every matching relation body once per labeled training stock-day."""
    if min_support < 1:
        raise ValueError("min_support must be positive")
    counts = defaultdict(Counter)
    seen = set()
    for stock, day, next_day, start, label in observations:
        if not day < next_day <= train_end or label not in {"UP", "DOWN"}:
            raise ValueError("Invalid training observation or label outside training window")
        key = stock, day
        if key in seen:
            raise ValueError(f"Duplicate training stock-day: {key}")
        seen.add(key)
        found = set()
        frontier = [()]
        for depth in range(1, 5):
            frontier = [
                path
                for prefix in frontier
                for path in graph.expand(start, prefix, day)
            ]
            if depth >= 2:
                found.update(map(body, frontier))
        for pattern in found:
            counts[pattern][label] += 1
    rules = []
    for pattern, labels in sorted(counts.items(), key=lambda pair: (len(pair[0]), pair[0])):
        support = sum(labels.values())
        for label, count in sorted(labels.items()):
            confidence = count / support
            if support >= min_support and confidence >= threshold:
                # The paper leaves the subsumption test unspecified. Prune a longer
                # rule if a retained prefix has equal or better confidence and support.
                redundant = any(
                    r.label == label
                    and pattern[:len(r.body)] == r.body
                    and r.confidence >= confidence
                    and r.support >= support
                    for r in rules
                )
                if not redundant:
                    rules.append(Rule(pattern, label, support, confidence))
    return rules


def predict(graph, start, as_of, rules, *, select, validate, alpha,
            width=8, depth=3, threshold=0.60, evidence_budget=5, path_budget=10):
    """Run Algorithm 1 with supplied relation-selection and validation controllers.

    select(paths) yields a subset of candidate paths. validate(path, rule)
    returns a label and plausibility. The adapters receive text via their closure.
    """
    if not 0 <= alpha <= 1 or min(width, depth, evidence_budget, path_budget) < 1:
        raise ValueError("Invalid search configuration")
    prefixes = defaultdict(list)
    for rule in rules:
        for length in range(1, len(rule.body) + 1):
            prefixes[rule.body[:length]].append(rule)

    def completed(path):
        pattern = body(path)
        return [
            r for r in prefixes[pattern]
            if r.body == pattern and r.confidence >= threshold
        ]

    def rank(path):
        pattern = body(path)
        coverage = max(len(pattern) / len(r.body) for r in prefixes[pattern])
        nodes = (start, *(edge.target for edge in path))
        return (
            not completed(path), -coverage, -max(
                int(edge.published.replace("-", "")) for edge in path
            ),
            sum(graph.degree(node, as_of) for node in nodes),
            len(path),
            sha256(repr(path).encode()).hexdigest(),
        )

    beam = [()]
    hypotheses = []
    for _ in range(depth):
        candidates = [
            path
            for prefix in beam
            for path in graph.expand(start, prefix, as_of)
            if body(path) in prefixes
        ]
        if not candidates:
            break
        ranked = sorted(candidates, key=rank)
        # Algorithm 1 collects completed hypotheses before relation pruning.
        hypotheses.extend((path, rule) for path in ranked for rule in completed(path))
        allowed = set(select(tuple(ranked)))
        if not allowed.issubset(candidates):
            raise ValueError("Relation selector returned a path outside the candidate set")
        beam = [
            path for path in ranked if path in allowed and path[-1].target not in graph.text_sources
        ][:width]

    if not hypotheses:
        return "DOWN", 0.0, []
    hypotheses.sort(key=lambda pair: (rank(pair[0]), -pair[1].confidence, pair[1].label))
    best = {
        label: max((r.confidence for _, r in hypotheses if r.label == label), default=0.0)
        for label in ("UP", "DOWN")
    }
    label = "UP" if best["UP"] >= best["DOWN"] else "DOWN"
    evidence = []
    for path, rule in hypotheses[:path_budget]:
        verdict, plausibility = validate(path, rule)
        if verdict not in {"UP", "DOWN"} or not 0 <= plausibility <= 1:
            raise ValueError("Invalid evidence-controller verdict")
        if verdict == rule.label == label:
            score = alpha * rule.confidence + (1 - alpha) * plausibility
            evidence.append((score, path, rule))
    evidence.sort(key=lambda item: (-item[0], rank(item[1])))
    return label, best[label], evidence[:evidence_budget]
