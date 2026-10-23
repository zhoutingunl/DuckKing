"""Small libopus binding: 16 kHz uplink and negotiated mono downlink."""

import ctypes as C
import ctypes.util
import os
from pathlib import Path


class OpusCodec:
    def __init__(self, sample_rate=16000):
        if sample_rate not in {8000, 12000, 16000, 24000, 48000}:
            raise ValueError("不支持的 Opus 采样率")
        path = os.getenv("DUCKKING_OPUS_LIBRARY") or ctypes.util.find_library("opus")
        if not path:
            path = next(
                (
                    str(p)
                    for p in [
                        Path("/opt/homebrew/lib/libopus.dylib"),
                        Path("/usr/local/lib/libopus.dylib"),
                    ]
                    if p.is_file()
                ),
                None,
            )
        if not path:
            raise RuntimeError("未找到 libopus；macOS 执行 brew install opus")
        self.lib = C.CDLL(path)
        self.sample_rate = sample_rate
        self.lib.opus_encoder_create.argtypes = [C.c_int, C.c_int, C.c_int, C.POINTER(C.c_int)]
        self.lib.opus_encoder_create.restype = C.c_void_p
        self.lib.opus_decoder_create.argtypes = [C.c_int, C.c_int, C.POINTER(C.c_int)]
        self.lib.opus_decoder_create.restype = C.c_void_p
        self.lib.opus_encode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_int16),
            C.c_int,
            C.POINTER(C.c_ubyte),
            C.c_int,
        ]
        self.lib.opus_decode.argtypes = [
            C.c_void_p,
            C.POINTER(C.c_ubyte),
            C.c_int,
            C.POINTER(C.c_int16),
            C.c_int,
            C.c_int,
        ]
        self.lib.opus_encoder_destroy.argtypes = [C.c_void_p]
        self.lib.opus_decoder_destroy.argtypes = [C.c_void_p]
        error = C.c_int()
        self.encoder = self.lib.opus_encoder_create(sample_rate, 1, 2048, C.byref(error))
        if error.value or not self.encoder:
            raise RuntimeError("Opus encoder 初始化失败")
        self.decoder = self.lib.opus_decoder_create(sample_rate, 1, C.byref(error))
        if error.value or not self.decoder:
            self.lib.opus_encoder_destroy(self.encoder)
            self.encoder = None
            raise RuntimeError("Opus decoder 初始化失败")

    def encode(self, pcm: bytes) -> bytes:
        samples = self.sample_rate * 60 // 1000
        if len(pcm) != samples * 2:
            raise ValueError("上行需要恰好 60ms 的单声道 PCM16")
        source = (C.c_int16 * samples).from_buffer_copy(pcm)
        output = (C.c_ubyte * 4000)()
        count = self.lib.opus_encode(self.encoder, source, samples, output, len(output))
        if count < 0:
            raise ValueError("Opus 编码失败")
        return bytes(output[:count])

    def decode(self, packet: bytes) -> bytes:
        if not packet or len(packet) > 65536:
            raise ValueError("无效的 Opus 音频包")
        source = (C.c_ubyte * len(packet)).from_buffer_copy(packet)
        output = (C.c_int16 * (self.sample_rate * 120 // 1000))()
        count = self.lib.opus_decode(self.decoder, source, len(packet), output, len(output), 0)
        if count < 0:
            raise ValueError("Opus 解码失败")
        return C.string_at(C.addressof(output), count * 2)

    def close(self):
        if self.encoder:
            self.lib.opus_encoder_destroy(self.encoder)
            self.encoder = None
        if self.decoder:
            self.lib.opus_decoder_destroy(self.decoder)
            self.decoder = None
