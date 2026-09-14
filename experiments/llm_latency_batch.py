#!/usr/bin/env python3
"""Per-inference latency for the intent parsers, measured on the production prompt.

    python3 experiments/llm_latency_batch.py hailo
    python3 experiments/llm_latency_batch.py cpu

WHY THIS EXISTS. FRD G-6 recorded accuracy for both backends but never a time. The only latency
figure in the repo is config.py:511 -- a full voice turn of stt=12.1s intent=0.0s tts=4.6s
total=16.7s for "What time is it?" -- and that intent=0.0s is the FAST PATH (voice.py answers
time/date directly without ever calling a model), so the LLM's own cost has never appeared in it.

Before the 2026-09-14 ChatML fix the Hailo path was producing 820-1039 character completions and
informal timings ranged from 12s to over two minutes. After the fix completions are ~110
characters. Whether that translated into a usable response time is the open question FR-1500
turns on, and it is not answerable from the accuracy batch.

This deliberately drives the SAME ask_sync() path and the SAME prompt as
experiments/llm_reliability_batch.py, because a latency number measured against a different
prompt would not describe the rover.

Reports median and p90 rather than a mean: one 60s outlier drags a mean somewhere that describes
no actual utterance, and what a person experiences is the typical wait and the bad-but-plausible
wait.
"""
import sys
import os
import time
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_reliability_batch import TEST_CASES, _build_prompt

SCHEMA = {'intent': str, 'args': dict, 'reply': str}

# From config.py:511, measured live on this rover 2026-08-21.
STT_S = 12.1
TTS_S = 4.6


def main():
    backend = sys.argv[1] if len(sys.argv) > 1 else 'cpu'
    if backend == 'cpu':
        from ai_provider import LocalAIProvider
        provider = LocalAIProvider()
    elif backend == 'hailo':
        from hailo_llm import HailoIntentModel
        provider = HailoIntentModel()
    else:
        print(f'Unknown backend {backend!r} -- use "cpu" or "hailo"')
        return 2

    if not provider.available:
        print(f'{backend} provider is not available on this machine')
        return 1

    times = []
    for utterance, expected_intent, _ in TEST_CASES:
        t0 = time.perf_counter()
        result = provider.ask_sync(_build_prompt(utterance), schema=SCHEMA)
        dt = time.perf_counter() - t0
        times.append(dt)
        got = (result.payload or {}).get('intent') if result.parse_success else None
        print(f'{dt:7.2f}s  [{expected_intent}] -> {got!r}', flush=True)

    # The scorer that burned this investigation silently counted 15 of 32 records. Never report a
    # statistic without first checking the sample is the size it should be.
    n = len(times)
    assert n == len(TEST_CASES), f'timed {n} cases, expected {len(TEST_CASES)}'

    times_sorted = sorted(times)
    p90 = times_sorted[int(0.9 * (n - 1))]
    median = statistics.median(times)

    print(f'\n--- {backend}, n={n} ---')
    print(f'  min    {min(times):7.2f}s')
    print(f'  median {median:7.2f}s')
    print(f'  p90    {p90:7.2f}s')
    print(f'  max    {max(times):7.2f}s')
    print(f'  total  {sum(times):7.1f}s')
    print(f'\nProjected full voice turn (stt {STT_S}s + intent + tts {TTS_S}s), '
          f'using config.py:511 measurements:')
    print(f'  median case {STT_S + median + TTS_S:6.1f}s')
    print(f'  p90 case    {STT_S + p90 + TTS_S:6.1f}s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
