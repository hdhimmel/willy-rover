#!/usr/bin/env python3
"""Classify every case of the 32-case intent benchmark, with raw output, to answer ONE question:

    WHY does Hailo produce CONFIDENT WRONG answers?

    python3 experiments/classify_failures.py --repeats 3

Requested by the 2026-09-14 review, which correctly said not to spend another pass blindly
tuning temperature/top_p. The previous qualification run recorded the PARSED payload but not the
model's raw text, so a parse failure was a dead end -- "parse failed: Expecting value" tells you
where json.loads gave up, not what the model said. That is the same mistake that let the original
0% be misdiagnosed as truncation for three weeks. Raw output is captured here by wrapping
generate_all() in the harness, so production code is untouched.

CATEGORIES (hierarchical -- first match wins, so counts sum to n):

    parse_failure           no usable JSON came back at all
    confident_wrong         parsed, intent WRONG, self-reported confidence >= floor.
                            The dangerous class and the subject of the review's question.
    wrong_intent            parsed, intent wrong, confidence below floor -- the model at least
                            signalled doubt, so the voice path would escalate rather than act
    normalization_gap       intent CORRECT but the batch scores it a failure on args shape.
                            Inert on the rover (brain.py reads args only for retrieve/go_to/
                            movement) so this is a benchmark artifact, counted separately rather
                            than hidden inside a pass rate
    rejected_by_confidence  intent CORRECT but confidence below LOCAL_LLM_CONFIDENCE_FLOOR, so
                            voice.py would escalate a right answer to the cloud
    actionable              correct intent, usable args, has a reply
    other                   anything the above did not describe -- should be empty; if it is not,
                            the taxonomy is wrong and needs extending rather than ignoring

The CPU column comes from the committed CPU qualification artifact so the two are compared on the
same utterances without re-running a 13-minute batch.
"""
import sys
import os
import time
import json
import argparse
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from llm_reliability_batch import TEST_CASES, _build_prompt

SCHEMA = {'intent': str, 'args': dict, 'reply': str}
ARGS_CONSUMING = {'retrieve', 'go_to', 'forward', 'reverse', 'turn_left', 'turn_right'}
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')


class _RawCapture:
    """Wraps the provider's LLM so the raw completion is recorded alongside the parsed result.
    Wrapping here rather than adding a debug field to hailo_llm.py keeps a measurement concern
    out of the production path."""

    def __init__(self, inner):
        self._inner = inner
        self.last_raw = None

    def generate_all(self, prompt, **kw):
        txt = self._inner.generate_all(prompt, **kw)
        self.last_raw = txt
        return txt

    def clear_context(self):
        return self._inner.clear_context()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def classify(expected, expects_args, result, floor):
    payload = result.payload or {}
    if not result.parse_success:
        return 'parse_failure'
    conf = result.intent_confidence
    if payload.get('intent') != expected:
        return 'confident_wrong' if conf >= floor else 'wrong_intent'
    # intent is correct from here on
    if 'reply' not in payload:
        return 'other'
    if expected in ARGS_CONSUMING and not (payload.get('args') or {}).get('object'):
        return 'normalization_gap'
    if bool(payload.get('args')) != expects_args:
        return 'normalization_gap'
    if conf < config.LOCAL_LLM_CONFIDENCE_FLOOR:
        return 'rejected_by_confidence'
    return 'actionable'


def load_cpu():
    """Best CPU answer per utterance, from the committed artifact."""
    path = os.path.join(RESULTS, '2026-09-14-cpu-qualification.json')
    if not os.path.exists(path):
        return {}
    out = {}
    for r in json.load(open(path))['records']:
        out.setdefault(r['utterance'], (r['outcome'], (r['payload'] or {}).get('intent')))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repeats', type=int, default=3)
    args = ap.parse_args()

    from hailo_llm import HailoIntentModel
    provider = HailoIntentModel()
    if not provider.available:
        print('hailo unavailable')
        return 1
    provider._llm = _RawCapture(provider._llm)

    floor = config.HAILO_LLM_CONFIDENCE_FLOOR
    cpu = load_cpu()
    records = []

    for rep in range(args.repeats):
        for utterance, expected, expects_args in TEST_CASES:
            t0 = time.perf_counter()
            result = provider.ask_sync(_build_prompt(utterance), schema=SCHEMA)
            dt = time.perf_counter() - t0
            raw = provider._llm.last_raw
            cat = classify(expected, expects_args, result, floor)
            cpu_outcome, cpu_intent = cpu.get(utterance, (None, None))
            records.append({
                'repeat': rep,
                'utterance': utterance,
                'expected_intent': expected,
                'expects_args': expects_args,
                'raw_output': raw,
                'raw_len': len(raw) if raw else 0,
                'normalized_payload': result.payload,
                'parsed_intent': (result.payload or {}).get('intent'),
                'confidence': result.intent_confidence,
                'self_reported_confidence': (result.payload or {}).get('confidence'),
                'actionable': cat == 'actionable',
                'category': cat,
                'parse_reason': result.reason,
                'cpu_outcome': cpu_outcome,
                'cpu_intent': cpu_intent,
                'latency_s': round(dt, 2),
            })
            print(f'  rep{rep} {cat:22s} [{expected}] -> {records[-1]["parsed_intent"]!r}',
                  flush=True)

    n = len(records)
    assert n == args.repeats * len(TEST_CASES), f'{n} records, expected {args.repeats * len(TEST_CASES)}'

    cats = Counter(r['category'] for r in records)
    # Per-utterance consistency: a failure that repeats every time is a property of the model,
    # one that comes and goes is sampling noise. They need different fixes.
    per_utt = defaultdict(list)
    for r in records:
        per_utt[r['utterance']].append(r['category'])
    always_fail = {u: c[0] for u, c in per_utt.items()
                   if len(set(c)) == 1 and c[0] != 'actionable'}
    intermittent = {u: c for u, c in per_utt.items() if len(set(c)) > 1}

    summary = {
        'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'n': n, 'repeats': args.repeats,
        'categories': dict(cats),
        'deterministic_failures': always_fail,
        'intermittent_cases': {u: c for u, c in intermittent.items()},
        'config': {'temperature': config.HAILO_LLM_TEMPERATURE,
                   'top_p': config.HAILO_LLM_TOP_P,
                   'max_tokens': config.HAILO_LLM_MAX_TOKENS,
                   'hailo_floor': floor,
                   'voice_floor': config.LOCAL_LLM_CONFIDENCE_FLOOR},
    }

    out = os.path.join(RESULTS, f'{time.strftime("%Y-%m-%d")}-hailo-failure-classification.json')
    os.makedirs(RESULTS, exist_ok=True)
    with open(out, 'w') as f:
        json.dump({'summary': summary, 'records': records}, f, indent=2)

    print(json.dumps(summary, indent=2))
    print(f'\nArtifact: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
