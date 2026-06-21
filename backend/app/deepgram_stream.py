"""Milestone 1 — Deepgram streaming speech-to-text.

The frontend opens a WebSocket and pipes raw mic audio in. We forward that
to Deepgram's live endpoint and stream interim + final transcripts back out
so words appear on screen as the person speaks.
"""
import os
# macOS python.org builds don't use the system CA store; point SSL at certifi's
# bundle so the TLS handshake to Deepgram verifies (only if not already set).
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:
    pass
from deepgram import Deepgram

DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]

async def make_live_connection(on_transcript, on_utterance_end):
    dg = Deepgram(DEEPGRAM_API_KEY)
    socket = await dg.transcription.live({
        "smart_format": True,
        "model": "nova-2",
        "interim_results": True,
        "endpointing": 500,        # give more pause before speech_final
        "utterance_end_ms": 1500,  # ms of silence before utterance_end fires
        "punctuate": True,
        "filler_words": False,
        "encoding": "linear16",
        "sample_rate": 16000,
        "channels": 1,
    })

    def handle_transcript(data):
        if "channel" not in data:
            return
        alt = data["channel"]["alternatives"][0]
        text = alt.get("transcript", "")
        is_final = data.get("is_final", False)
        if text:
            on_transcript(text, is_final)
        if data.get("speech_final"):
            on_utterance_end()

    socket.registerHandler(socket.event.TRANSCRIPT_RECEIVED, handle_transcript)
    return socket
