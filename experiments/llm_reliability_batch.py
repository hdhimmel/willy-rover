# JSON-reliability test harness for voice.py::_interpret_local()'s prompt, against any backend
# exposing ai_provider.py::AIProvider.ask_sync(prompt,system=None,schema=None,history=None).
# Built and smoke-tested against the current CPU LocalAIProvider as a control before ever
# pointing it at a Hailo model -- see docs/superpowers/plans/2026-08-23-hailo-voice-offload.md
# Task 3. Every utterance below deliberately carries filler words the fast-path regex in
# voice.py::_FAST_PATH_PATTERNS would reject, since this harness is specifically for the
# utterances that miss the fast path and reach the LLM.

TEST_CASES = [
    # (utterance, expected_intent, expects_args)
    ("can you go fetch the red ball for me", "retrieve", True),
    ("grab the blue cup off the floor", "retrieve", True),
    ("I need you to bring me my slippers", "retrieve", True),
    ("could you pick up the remote from the couch", "retrieve", True),

    ("I think it's time you went to sleep", "shutdown", False),
    ("would you power yourself off now", "shutdown", False),
    ("go ahead and shut yourself down", "shutdown", False),

    ("how's your status looking today", "status", False),
    ("are you doing okay buddy", "status", False),
    ("can I get a status report please", "status", False),

    ("what's your charge level at right now", "battery", False),
    ("do you have much juice left", "battery", False),
    ("how much battery do you have left", "battery", False),

    ("could you stow your arm away please", "arm_stow", False),
    ("put that arm away for me", "arm_stow", False),
    ("go ahead and stow the arm", "arm_stow", False),

    ("can you reset your arm back home", "arm_home", False),
    ("send your arm home please", "arm_home", False),

    ("hey come over here for a second", "come_here", False),
    ("could you come here please", "come_here", False),

    ("start following me around", "follow", False),
    ("keep following me for a while", "follow", False),

    ("can you run a self test for me", "diagnostics", False),
    ("go run diagnostics please", "diagnostics", False),

    ("do you know what room this is", "where_are_you", False),
    ("can you tell me where you are right now", "where_are_you", False),

    ("what do you see out there right now", "what_do_you_see", False),
    ("can you tell me what's in front of you", "what_do_you_see", False),

    ("could you give everyone a wave", "wave", False),
    ("go ahead and say hi to them", "wave", False),

    ("whoa whoa please stop right now", "stop", False),
    ("I need you to stop moving immediately", "stop", False),
]


# Mirrors voice.py::_interpret_local()'s exact prompt construction (voice.py:374-395) --
# without this, the model has no instruction to respond in JSON at all and just replies
# conversationally, which is what happened on the first (buggy) run of this harness: every
# case failed identically with "substring not found" because the raw model output contained
# no '{' for ai_provider.py::_parse_response() to find. Keep this in sync with voice.py's
# real prompt if that prompt ever changes -- it's duplicated rather than imported so this
# harness stays decoupled from voice.py's VoicePipeline construction (which needs a live mic).
def _build_prompt(text):
    return (f'You are Willie, a home-assistant rover. Known facts: {{}}\n'
            f'User said: "{text}"\n'
            f'If the user is asking you to fetch/bring/collect an object -- phrasings like '
            f'"retrieve", "get", "pick up", "grab", or "bring me" the object -- use '
            f'intent "retrieve" with args {{"object":"<the object>"}}, regardless of which '
            f'of those words they used.\n'
            f'Other recognized intents and example phrasings, always use exactly these names:\n'
            f'"shutdown" -- "shut down", "power off", "go to sleep"\n'
            f'"status" -- "how are you?", "status report", "are you okay?"\n'
            f'"battery" -- "how\'s your battery?", "how much charge left?"\n'
            f'"arm_stow" -- "stow the arm", "put your arm away"\n'
            f'"arm_home" -- "arm home", "reset your arm"\n'
            f'"come_here" -- "come here", "come over here"\n'
            f'"follow" -- "follow me", "keep following me"\n'
            f'"diagnostics" -- "run diagnostics", "self test"\n'
            f'"where_are_you" -- "where are you?", "what room is this?"\n'
            f'"what_do_you_see" -- "what do you see?", "what\'s in front of you?"\n'
            f'"wave" -- "wave hello", "say hi", "give a wave"\n'
            f'"stop" -- "stop", "halt", "freeze"\n'
            f'Respond ONLY with JSON: '
            f'{{"intent":"<short action name>","args":{{}},"reply":"<what to say back, <200 chars>",'
            f'"confidence":<0.0-1.0, how sure you are of this interpretation>}}')


def run_batch(provider, cases):
    results = []
    for utterance, expected_intent, expects_args in cases:
        result = provider.ask_sync(_build_prompt(utterance), schema={'intent': str, 'args': dict, 'reply': str})
        ok = (result.parse_success
              and result.payload.get('intent') == expected_intent
              and (bool(result.payload.get('args')) == expects_args))
        results.append((utterance, expected_intent, ok, result.payload, result.reason))
    passed = sum(1 for *_, ok, _, _ in results if ok)
    return results, passed / len(cases)


if __name__ == '__main__':
    import sys
    backend = sys.argv[1] if len(sys.argv) > 1 else 'cpu'
    if backend == 'cpu':
        from ai_provider import LocalAIProvider
        provider = LocalAIProvider()
    elif backend == 'hailo':
        from hailo_llm import HailoIntentModel
        provider = HailoIntentModel()
    else:
        print(f'Unknown backend {backend!r} -- use "cpu" or "hailo"')
        sys.exit(1)

    results, rate = run_batch(provider, TEST_CASES)
    for utterance, expected, ok, payload, reason in results:
        status = 'OK  ' if ok else 'FAIL'
        print(f'{status} [{expected}] {utterance!r} -> {payload} ({reason})')
    print(f'\nPass rate ({backend}): {rate:.0%} ({sum(1 for *_,ok,_,_ in results if ok)}/{len(results)})')
