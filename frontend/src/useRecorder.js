import { useRef, useState, useCallback } from "react";

/**
 * useRecorder — captures the mic and streams raw audio to the backend
 * WebSocket (/ws/transcribe). Emits partial transcripts as they arrive and
 * node batches when the speaker pauses.
 *
 * Deepgram wants linear16 PCM; the simplest reliable path in-browser is to
 * capture via an AudioWorklet/ScriptProcessor and send Int16 frames. For the
 * hackathon, MediaRecorder with audio/webm also works if you set Deepgram's
 * encoding accordingly — keep whichever your Deepgram options match.
 */
export function useRecorder({ onPartial, onNodes }) {
  const [recording, setRecording] = useState(false);
  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const ctxRef = useRef(null);

  const start = useCallback(async () => {
    const ws = new WebSocket(`ws://localhost:8000/ws/transcribe`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "partial") onPartial?.(msg.text);
      if (msg.type === "nodes") onNodes?.(msg.nodes);
    };

    await new Promise((res) => (ws.onopen = res));

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;

    const ctx = new AudioContext({ sampleRate: 16000 });
    ctxRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    const processor = ctx.createScriptProcessor(4096, 1, 1);

    processor.onaudioprocess = (ev) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      const input = ev.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        const s = Math.max(-1, Math.min(1, input[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      ws.send(pcm.buffer);
    };

    source.connect(processor);
    processor.connect(ctx.destination);
    setRecording(true);
  }, [onPartial, onNodes]);

  const stop = useCallback(() => {
    ctxRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    wsRef.current?.close();
    setRecording(false);
  }, []);

  return { recording, start, stop };
}
