"use client";

import { useEffect, useRef } from "react";

interface Star {
  x: number;
  y: number;
  r: number;
  a: number;
  tw: number;
  ts: number;
}

interface Nebula {
  x: number;
  y: number;
  r: number;
  hue: number;
}

interface ShootingStar {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
}

const STAR_COUNT = 250;

/** Fixed, full-viewport canvas rendered behind the app (z-index handled
 * by the caller). Purely decorative — no interaction, no layout impact. */
export function GalaxyBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let stars: Star[] = [];
    let nebulae: Nebula[] = [];
    let shootingStars: ShootingStar[] = [];
    let raf = 0;
    let nextShootAt = 0;

    const resize = () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    const init = () => {
      stars = Array.from({ length: STAR_COUNT }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        r: Math.random() * 1.2 + 0.3,
        a: Math.random() * 0.7 + 0.3,
        tw: Math.random() * Math.PI * 2,
        ts: Math.random() * 0.015 + 0.005,
      }));
      nebulae = [
        { x: width * 0.12, y: height * 0.18, r: 260, hue: 200 },
        { x: width * 0.85, y: height * 0.7, r: 220, hue: 260 },
        { x: width * 0.6, y: height * 0.1, r: 180, hue: 190 },
        { x: width * 0.3, y: height * 0.9, r: 200, hue: 280 },
      ];
      nextShootAt = performance.now() + 3000 + Math.random() * 2000;
    };

    const spawnShootingStar = () => {
      shootingStars.push({
        x: Math.random() * width * 0.6,
        y: Math.random() * height * 0.35,
        vx: 6 + Math.random() * 6,
        vy: 4 + Math.random() * 4,
        life: 1,
      });
    };

    const draw = (now: number) => {
      ctx.fillStyle = "#020818";
      ctx.fillRect(0, 0, width, height);

      const pulse = 0.5 + 0.5 * Math.sin(now / 2000);
      for (const n of nebulae) {
        const gradient = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r);
        const alpha = 0.05 + 0.03 * pulse;
        gradient.addColorStop(0, `hsla(${n.hue}, 70%, 45%, ${alpha})`);
        gradient.addColorStop(1, "transparent");
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fill();
      }

      for (const s of stars) {
        s.tw += s.ts;
        const brightness = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(s.tw));
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(200, 220, 255, ${brightness * s.a})`;
        ctx.fill();
      }

      if (now >= nextShootAt) {
        spawnShootingStar();
        nextShootAt = now + 3000 + Math.random() * 2000;
      }
      shootingStars = shootingStars.filter((s) => s.life > 0);
      for (const s of shootingStars) {
        const tailX = s.x - s.vx * 10;
        const tailY = s.y - s.vy * 10;
        const gradient = ctx.createLinearGradient(s.x, s.y, tailX, tailY);
        gradient.addColorStop(0, `rgba(255, 255, 255, ${s.life})`);
        gradient.addColorStop(1, "transparent");
        ctx.strokeStyle = gradient;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(tailX, tailY);
        ctx.stroke();
        s.x += s.vx;
        s.y += s.vy;
        s.life -= 0.02;
      }

      raf = requestAnimationFrame(draw);
    };

    resize();
    init();
    raf = requestAnimationFrame(draw);

    const onResize = () => {
      resize();
      init();
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none fixed inset-0"
      style={{ zIndex: 0 }}
      aria-hidden="true"
    />
  );
}
