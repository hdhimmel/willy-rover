#!/usr/bin/env python3
"""Qualification run for the on-device intent parser: accuracy, stability, calibration, latency.

    python3 experiments/hailo_qualification.py hailo --repeats 3
    python3 experiments/hailo_qualification.py cpu   --repeats 3

Answers three questions in ONE pass over a single long-lived provider, because they are not
independent -- stability can only be judged across the same instance that produced the accuracy
numbers, and confidence calibration needs the per-case confidence from those same calls.

P0-1  ACCURACY. Overall, plus the breakdown that matters: parse failures and wrong-intent
      failures are different defects with different fixes, and a single pass rate hides which one
      is happening.

P0-2  REPEATED-CALL STABILITY. The 2026-08-23 defect was that generate_all() accumulates
      conversation context: call 1 worked, later calls degraded, and it ended in "Conversation
      context is full". That is invisible to any test that builds a fresh model per case. So this
      builds ONE provider and drives the whole 32-case sequence through it N times, then reports
      per-repeat scores. A real context leak shows up as monotonic decay across repeats; noise
      does not.

P0-3  CONFIDENCE CALIBRATION. HAILO_LLM_CONFIDENCE_FLOOR=0.7 is the gate that decides whether an
      on-device answer drives the rover or escalates to the cloud. A self-reported confidence is
      not automatically calibrated, and nobody had checked. The number that matters is
      PRECISION ABOVE THE FLOOR: of the answers scoring >= 0.7, what fraction are actually right?
      That is the rate at which a wrong decision reaches arbitration unchallenged.

LATENCY is recorded per call because it is free to collect here and FR-1500 is a speech
requirement.

Everything is written to a JSON artifact under experiments/results/. The point is that the
numbers in FRD G-6 stop being prose somebody has to trust: the raw per-case records, including
every payload, go in the repo next to the conclusion drawn from them.
"""
import sys
import os
import time
import json
import argparse
import statistics
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from llm_reliability_batch import TEST_CASES, _build_prompt

SCHEMA = {'intent': str, 'args': dict, 'reply': str}

# brain.py reads args only for these; for every other intent a stray args is inert on the rover
# (verified brain.py:753-781). Kept in sync with experiments' actionable metric.
ARGS_CONSUMING = {'retrieve', 'go_to', 'forward', 'reverse', 'turn_left', 'turn_right'}


def classify(expected, expects_args, result):
    """One case -> an outcome label. Deliberately distinguishes the failure KINDS, because
    'parse failed' and 'confidently wrong intent' need opposite fixes and only one of them is
    dangerous."""
    if not result.parse_success:
        return 'parse_failure'
    payload = result.payload or {}
    if payload.get('intent') != expected:
        return 'wrong_intent'
    if 'reply' not in payload:
        return 'no_reply'
    if expected in ARGS_CONSUMING:
        a = payload.get('args') or {}
        if not a.get('object') and not a.get('room'):
            return 'missing_args'
    # Correct intent, usable args, something to say. The batch's own scorer additionally
    # requires bool(args) == expects_args; that is recorded separately as strict_pass.
    return 'actionable'


def run(provider, repeats):
    records = []
    for rep in range(repeats):
        for utterance, expected, expects_args in TEST_CASES:
            t0 = time.perf_counter()
            try:
                result = provider.ask_sync(_build_prompt(utterance), schema=SCHEMA)
                raised = None
            except Exception as e:                      # must never happen; recorded if it does
                dt = time.perf_counter() - t0
                records.append({'repeat': rep, 'utterance': utterance, 'expected': expected,
                                'outcome': 'exception', 'raised': f'{type(e).__name__}: {e}',
                                'latency_s': round(dt, 3), 'confidence': None, 'payload': None,
                                'strict_pass': False})
                continue
            dt = time.perf_counter() - t0
            payload = result.payload or {}
            outcome = classify(expected, expects_args, result)
            strict = (result.parse_success
                      and payload.get('intent') == expected
                      and (bool(payload.get('args')) == expects_args))
            records.append({
                'repeat': rep,
                'utterance': utterance,
                'expected': expected,
                'outcome': outcome,
                'raised': None,
                'latency_s': round(dt, 3),
                'confidence': payload.get('confidence') if result.parse_success else None,
                'intent_confidence': round(result.intent_confidence, 3),
                'payload': payload if result.parse_success else None,
                'reason': result.reason,
                'strict_pass': bool(strict),
            })
            print(f'  rep{rep} {dt:6.2f}s {outcome:14s} [{expected}] -> '
                  f'{payload.get("intent")!r}', flush=True)
    return records


def summarise(records, repeats, backend):
    n = len(records)
    expected_n = repeats * len(TEST_CASES)
    # The G-6 investigation produced a table from a scorer that silently counted 15 of 32
    # records. Never report a statistic without proving the sample is the size it should be.
    assert n == expected_n, f'got {n} records, expected {expected_n}'

    outcomes = Counter(r['outcome'] for r in records)
    actionable = outcomes['actionable']
    strict = sum(1 for r in records if r['strict_pass'])
    lat = [r['latency_s'] for r in records]
    lat_sorted = sorted(lat)

    # P0-2: per-repeat, to expose monotonic decay rather than average it away.
    per_repeat = []
    for rep in range(repeats):
        sub = [r for r in records if r['repeat'] == rep]
        per_repeat.append({
            'repeat': rep,
            'n': len(sub),
            'actionable': sum(1 for r in sub if r['outcome'] == 'actionable'),
            'parse_failures': sum(1 for r in sub if r['outcome'] == 'parse_failure'),
            'median_latency_s': round(statistics.median(r['latency_s'] for r in sub), 2),
        })

    # P0-3: precision above and below the configured floor.
    floor = config.HAILO_LLM_CONFIDENCE_FLOOR
    above = [r for r in records if (r['intent_confidence'] or 0) >= floor]
    below = [r for r in records if (r['intent_confidence'] or 0) < floor]
    above_ok = sum(1 for r in above if r['outcome'] == 'actionable')
    below_ok = sum(1 for r in below if r['outcome'] == 'actionable')

    return {
        'backend': backend,
        'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'config': {
            'temperature': getattr(config, 'HAILO_LLM_TEMPERATURE', None),
            'top_p': getattr(config, 'HAILO_LLM_TOP_P', None),
            'max_tokens': getattr(config, 'HAILO_LLM_MAX_TOKENS', None),
            'confidence_floor': floor,
            'model_path': getattr(config, 'HAILO_LLM_MODEL_PATH', None),
        },
        'n': n,
        'repeats': repeats,
        'cases_per_repeat': len(TEST_CASES),
        'outcomes': dict(outcomes),
        'actionable': actionable,
        'actionable_pct': round(100 * actionable / n, 1),
        'strict_pass': strict,
        'strict_pass_pct': round(100 * strict / n, 1),
        'latency': {
            'min_s': round(min(lat), 2),
            'median_s': round(statistics.median(lat), 2),
            'p90_s': round(lat_sorted[int(0.9 * (n - 1))], 2),
            'max_s': round(max(lat), 2),
        },
        'stability_per_repeat': per_repeat,
        'calibration': {
            'floor': floor,
            'at_or_above_floor': len(above),
            'at_or_above_floor_correct': above_ok,
            'precision_above_floor_pct': round(100 * above_ok / len(above), 1) if above else None,
            'below_floor': len(below),
            'below_floor_correct': below_ok,
            'escalated_but_would_have_been_right_pct': (
                round(100 * below_ok / len(below), 1) if below else None),
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('backend', choices=['hailo', 'cpu'])
    ap.add_argument('--repeats', type=int, default=3,
                    help='how many times to drive the whole 32-case sequence through ONE provider')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    if args.backend == 'cpu':
        from ai_provider import LocalAIProvider
        provider = LocalAIProvider()
    else:
        from hailo_llm import HailoIntentModel
        provider = HailoIntentModel()

    if not provider.available:
        print(f'{args.backend} provider unavailable')
        return 1

    print(f'{args.backend}: {args.repeats} x {len(TEST_CASES)} cases through ONE instance')
    records = run(provider, args.repeats)
    summary = summarise(records, args.repeats, args.backend)

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results',
                                   f'{time.strftime("%Y-%m-%d")}-{args.backend}-qualification.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as f:
        json.dump({'summary': summary, 'records': records}, f, indent=2)

    print(json.dumps(summary, indent=2))
    print(f'\nArtifact: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
