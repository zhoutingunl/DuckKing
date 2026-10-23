import ctypes
import math
import struct
from unittest.mock import MagicMock

import pytest

from duckking.opus import OpusCodec


def test_real_opus_roundtrip_and_negotiated_downlink_rate():
    source = OpusCodec(16000)
    target = OpusCodec(24000)
    pcm = struct.pack("<960h", *(int(5000 * math.sin(i * 0.1)) for i in range(960)))
    packet = source.encode(pcm)
    decoded = target.decode(packet)
    assert len(decoded) == 2880
    assert any(decoded)
    source.close()
    source.close()
    target.close()


def test_bad_audio_packets_and_encoding_errors(monkeypatch):
    codec = OpusCodec()
    with pytest.raises(ValueError):
        codec.encode(b"bad length")
    for packet in [b"", bytes(65537)]:
        with pytest.raises(ValueError):
            codec.decode(packet)
    monkeypatch.setattr(codec.lib, "opus_encode", lambda *args: -1)
    with pytest.raises(ValueError):
        codec.encode(bytes(1920))
    monkeypatch.setattr(codec.lib, "opus_decode", lambda *args: -1)
    with pytest.raises(ValueError):
        codec.decode(b"invalid")
    codec.close()


def test_bad_rate_missing_library_and_native_creation_failure(monkeypatch):
    with pytest.raises(ValueError):
        OpusCodec(44100)
    monkeypatch.delenv("DUCKKING_OPUS_LIBRARY", raising=False)
    monkeypatch.setattr("ctypes.util.find_library", lambda name: None)
    monkeypatch.setattr("duckking.opus.Path.is_file", lambda self: False)
    with pytest.raises(RuntimeError, match="libopus"):
        OpusCodec()
    monkeypatch.setenv("DUCKKING_OPUS_LIBRARY", "fake-for-test")
    fake = MagicMock()
    fake.opus_encoder_create.return_value = None
    monkeypatch.setattr(ctypes, "CDLL", lambda path: fake)
    with pytest.raises(RuntimeError, match="encoder"):
        OpusCodec()
    fake.opus_encoder_create.return_value = 123
    fake.opus_decoder_create.return_value = None
    with pytest.raises(RuntimeError, match="decoder"):
        OpusCodec()
    fake.opus_encoder_destroy.assert_called_once_with(123)
