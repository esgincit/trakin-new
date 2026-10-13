"use client";

import { useEffect, useRef } from "react";

/** Draw a signature with mouse, pen or finger. Calls onChange with a PNG data URL (or null when cleared). */
export function SignaturePad({ onChange }: { onChange: (png: string | null) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const dirty = useRef(false);

  useEffect(() => {
    const c = canvas.current!;
    const ratio = window.devicePixelRatio || 1;
    c.width = c.offsetWidth * ratio;
    c.height = c.offsetHeight * ratio;
    const ctx = c.getContext("2d")!;
    ctx.scale(ratio, ratio);
    ctx.lineWidth = 2.2;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#1a2a6c";
  }, []);

  const point = (e: React.PointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top] as const;
  };

  return (
    <div>
      <canvas ref={canvas} className="sigpad" aria-label="Draw your signature"
        onPointerDown={(e) => { drawing.current = true; const [x, y] = point(e); const ctx = canvas.current!.getContext("2d")!; ctx.beginPath(); ctx.moveTo(x, y); canvas.current!.setPointerCapture(e.pointerId); }}
        onPointerMove={(e) => { if (!drawing.current) return; const [x, y] = point(e); const ctx = canvas.current!.getContext("2d")!; ctx.lineTo(x, y); ctx.stroke(); dirty.current = true; }}
        onPointerUp={() => { drawing.current = false; if (dirty.current) onChange(canvas.current!.toDataURL("image/png")); }} />
      <button type="button" className="btn sm mt" onClick={() => {
        const c = canvas.current!;
        c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
        dirty.current = false;
        onChange(null);
      }}>Clear</button>
    </div>
  );
}
