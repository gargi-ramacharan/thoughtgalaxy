"""Milestone 1 — Deepgram streaming speech-to-text.

The frontend opens a WebSocket and pipes raw mic audio in. We forward that
to Deepgram's live endpoint and stream interim + final transcripts back out
so words appear on screen as the person speaks.
"""
import os
from deepgram import (
    DeepgramClient,
    LiveTranscriptionEvents,
    LiveOptions,
)

DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]


def make_live_connection(on_transcript, on_utterance_end):
    """Create a Deepgram live connection.

    on_transcript(text, is_final): called for every chunk; is_final marks a
        settled phrase you can safely classify.
    on_utterance_end(): called when the speaker pauses — a natural moment to
        send the accumulated text to Claude.
    """
    dg = DeepgramClient(DEEPGRAM_API_KEY)
    connection = dg.listen.websocket.v("1")

    def _on_message(_self, result, **kwargs):
        sentence = result.channel.alternatives[0].transcript
        if not sentence:
            return
        on_transcript(sentence, result.is_final)

    def _on_utterance_end(_self, *args, **kwargs):
        on_utterance_end()

    connection.on(LiveTranscriptionEvents.Transcript, _on_message)
    connection.on(LiveTranscriptionEvents.UtteranceEnd, _on_utterance_end)

    options = LiveOptions(
        model="nova-3",          # Deepgram's best general model
        language="en-US",
        smart_format=True,       # punctuation + capitalization
        interim_results=True,    # gives the live-typing effect
        utterance_end_ms="1000", # 1s pause = end of a thought
        vad_events=True,
    )
    connection.start(options)
    return connection
