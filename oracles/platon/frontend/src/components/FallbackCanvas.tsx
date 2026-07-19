import { useEffect, useRef } from "react";
import type { Telemetry } from "../lib/types";
import { phaseColor } from "../lib/types";

function drawGlowCircle(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  color: string,
  amp: number
) {
  const grad = ctx.createRadialGradient(x, y, 0, x, y, r * 2.2);
  grad.addColorStop(0, color);
  grad.addColorStop(0.4, color);
  grad.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(x, y, r * 2.2, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = `rgba(110, 231, 255, ${0.25 + amp * 0.4})`;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(x, y, r + 3, 0, Math.PI * 2);
  ctx.stroke();
}

export function FallbackCanvas({ telemetry }: { telemetry: Telemetry | null }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const tRef = useRef(0);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let frame = 0;
    const draw = () => {
      frame++;
      tRef.current = frame / 60;
      const t = tRef.current;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      canvas.width = w;
      canvas.height = h;

      const bg = ctx.createRadialGradient(w / 2, h * 0.35, 0, w / 2, h / 2, w * 0.8);
      bg.addColorStop(0, "#0a0a1a");
      bg.addColorStop(0.5, "#050508");
      bg.addColorStop(1, "#020204");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);

      for (let i = 0; i < 200; i++) {
        const x = ((i * 137 + frame) % 1000) / 1000 * w;
        const y = ((i * 89) % 1000) / 1000 * h;
        const a = 0.15 + (i % 7) * 0.05;
        ctx.fillStyle = `rgba(255,255,255,${a})`;
        ctx.fillRect(x, y, 1 + (i % 2), 1 + (i % 2));
      }

      if (!telemetry) {
        ctx.fillStyle = "#6ee7ff";
        ctx.font = "16px monospace";
        ctx.fillText("◌  opening 32D aperture…", w / 2 - 110, h / 2);
        return;
      }

      const cols = 8;
      const cellW = w / (cols + 1);
      const cellH = h / 5.5;
      const positions: { x: number; y: number; amp: number; phase: number }[] = [];

      telemetry.oscillators.amplitudes.forEach((amp, i) => {
        const row = Math.floor(i / cols);
        const col = i % cols;
        const x = (col + 1) * cellW;
        const y = (row + 1.2) * cellH;
        const pulse = Math.sin(t * 3 + telemetry.oscillators.phases[i]) * 4;
        positions.push({ x, y, amp, phase: telemetry.oscillators.phases[i] });
        drawGlowCircle(
          ctx,
          x,
          y + pulse,
          12 + amp * 28,
          phaseColor(telemetry.oscillators.phases[i], amp),
          amp
        );
      });

      // coupling lines
      for (let i = 0; i < positions.length; i++) {
        for (let j = i + 1; j < positions.length; j++) {
          const dp = Math.abs(positions[i].phase - positions[j].phase);
          const diff = Math.min(dp, Math.PI * 2 - dp);
          if (diff < 0.6) {
            ctx.strokeStyle = `rgba(110, 231, 255, ${0.08 + (1 - diff) * 0.2})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(positions[i].x, positions[i].y);
            ctx.lineTo(positions[j].x, positions[j].y);
            ctx.stroke();
          }
        }
      }

      const px = w / 2 + telemetry.projection.x * w * 0.22;
      const py = h / 2 + telemetry.projection.y * h * 0.18;
      const og = ctx.createRadialGradient(px, py, 0, px, py, 60);
      og.addColorStop(0, "rgba(110, 231, 255, 0.35)");
      og.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = og;
      ctx.beginPath();
      ctx.arc(px, py, 60, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = "#6ee7ff";
      ctx.lineWidth = 2;
      ctx.shadowColor = "#6ee7ff";
      ctx.shadowBlur = 12;
      const s = 20 + Math.sin(t * 2) * 4;
      ctx.beginPath();
      ctx.moveTo(px, py - s);
      ctx.lineTo(px + s * 0.86, py + s * 0.5);
      ctx.lineTo(px - s * 0.86, py + s * 0.5);
      ctx.closePath();
      ctx.stroke();
      ctx.shadowBlur = 0;

      ctx.fillStyle = "rgba(122, 132, 156, 0.9)";
      ctx.font = "11px monospace";
      ctx.fillText("2D mode · enable WebGL for full hologram", 16, h - 16);
    };

    draw();
    const id = setInterval(draw, 1000 / 60);
    return () => clearInterval(id);
  }, [telemetry]);

  return (
    <canvas
      ref={ref}
      style={{ width: "100%", height: "100%", display: "block" }}
      data-testid="fallback-canvas"
    />
  );
}
