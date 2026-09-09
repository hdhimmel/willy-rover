import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

import config
from voice import downsample_to_16k

# The mic swap of 2026-09-09 (Waveshare mic -> the capture-only USB PnP Sound Device) forced this.
# openwakeword needs 16kHz and the new mic's hardware offers only 48000 and 44100 -- see
# /proc/asound/card3/stream0. PortAudio exposes the raw `hw:` devices ONLY (no plug, no default,
# no PipeWire route), so ALSA cannot do the rate conversion for us and it has to happen here.
#
# 48000 is deliberate over 44100: it is an exact 3:1 ratio to 16000, so decimation is integer and
# the filter is cheap. 44100 would need fractional resampling on the wake-word hot path.

_WAKE_FRAME=1280      # openwakeword's 80ms block at 16kHz


def _tone(freq_hz,rate,n,amp=0.5):
    t=np.arange(n)/float(rate)
    return (np.sin(2*np.pi*freq_hz*t)*amp*32767).astype(np.int16)


def _dominant_hz(samples,rate):
    spec=np.abs(np.fft.rfft(samples.astype(np.float64)))
    return float(np.fft.rfftfreq(len(samples),1.0/rate)[int(np.argmax(spec))])


def _rms(samples):
    return float(np.sqrt(np.mean((samples.astype(np.float64)/32768.0)**2)))


def test_factor_of_one_is_an_exact_passthrough():
    """A 16kHz-native mic must cost nothing -- no filtering, no copy semantics to reason about."""
    frame=_tone(1000,16000,_WAKE_FRAME)
    out=downsample_to_16k(frame,1)
    assert np.array_equal(out,frame)
    assert out.dtype==np.int16


def test_48k_block_becomes_one_1280_sample_16k_frame():
    """The shape contract the wake model depends on: 3840 in at 48k -> exactly 1280 out at 16k."""
    out=downsample_to_16k(_tone(1000,48000,_WAKE_FRAME*3),3)
    assert len(out)==_WAKE_FRAME
    assert out.dtype==np.int16


def test_speech_band_tone_survives_the_conversion():
    """1kHz sits mid-speech-band. If decimation mangled amplitude or pitch the wake model would
    be scoring something that no longer sounds like the training data."""
    src=_tone(1000,48000,_WAKE_FRAME*3*8)
    out=downsample_to_16k(src,3)
    assert abs(_dominant_hz(out,16000)-1000)<40, _dominant_hz(out,16000)
    assert abs(_rms(out)-_rms(src))<0.05, (_rms(out),_rms(src))


def test_above_nyquist_content_is_filtered_out_not_aliased_down():
    """The whole reason for a filter rather than samples[::3].

    20kHz is way above 16kHz-sampling's 8kHz Nyquist. Naive striding folds it back into the
    speech band as a loud phantom tone, which is exactly the kind of thing that quietly poisons
    wake-word scoring. Proper decimation must attenuate it instead.
    """
    src=_tone(20000,48000,_WAKE_FRAME*3*8)
    filtered=downsample_to_16k(src,3)
    naive=src[::3]
    assert _rms(filtered)<0.02, f'not attenuated: {_rms(filtered)}'
    assert _rms(filtered)<_rms(naive)/5, (
        f'filtered {_rms(filtered)} is not meaningfully better than naive striding {_rms(naive)}')


def test_a_rate_that_is_not_a_whole_multiple_of_16k_is_rejected():
    """44100 is the trap: the mic offers it, it looks reasonable, and it silently is not an
    integer ratio. validate() must say so rather than let it reach the audio thread."""
    original=config.AUDIO_INPUT_RATE
    try:
        config.AUDIO_INPUT_RATE=44100
        assert any('AUDIO_INPUT_RATE' in p for p in config.validate()), config.validate()
        config.AUDIO_INPUT_RATE=48000
        assert not any('AUDIO_INPUT_RATE' in p for p in config.validate())
        config.AUDIO_INPUT_RATE=16000
        assert not any('AUDIO_INPUT_RATE' in p for p in config.validate())
    finally:
        config.AUDIO_INPUT_RATE=original
