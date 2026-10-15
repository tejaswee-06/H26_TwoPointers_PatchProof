import React, { useEffect, useRef } from 'react';

// Person 3's particle wave, retuned: electric-blue tint near the crest, pauses when off-screen
// or when the tab is hidden, and renders a single static frame under reduced motion.
export default function ParticleWave({ reducedMotion = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    let w = 0; let h = 0; let raf = 0; let t = 0; let visible = true;
    const reduce = reducedMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      const r = canvas.getBoundingClientRect();
      w = canvas.width = Math.floor(r.width * dpr); h = canvas.height = Math.floor(r.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (reduce) draw();
    };
    const light = document.documentElement.dataset.theme === 'light';
    function draw() {
      ctx.clearRect(0, 0, w, h);
      const W = w / dpr; const H = h / dpr;
      const gap = W < 700 ? 18 : 14;
      for (let x = -30; x < W + 30; x += gap) {
        for (let y = H * 0.24; y < H * 1.08; y += gap) {
          const nx = x / W; const ny = y / H;
          const wave = Math.sin(nx * 7 + t * 0.6 + ny * 3) * 34 + Math.sin(nx * 14 - t * 0.4 + ny * 2) * 14;
          const ridge = Math.sin(nx * 3.2 + t * 0.35) * H * 0.12;
          const yy = y + wave + ridge;
          const center = Math.abs(ny - 0.62);
          const alpha = Math.max(0.06, 0.62 - center * 0.75) * (0.7 + 0.3 * Math.sin(x * 0.02 + t));
          const crest = Math.max(0, 1 - center * 3.2);
          const r = light ? 40 : Math.round(205 - 150 * crest);
          const g = light ? 90 : Math.round(220 - 90 * crest);
          const b = light ? 200 : 255;
          ctx.beginPath();
          ctx.arc(x, yy, Math.max(0.6, 1.1 + Math.sin(nx * 9 + t + ny) * 0.5), 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${r},${g},${b},${light ? alpha * 0.55 : alpha})`;
          ctx.fill();
        }
      }
    }
    const loop = () => { if (visible && !document.hidden) { t += 0.008; draw(); } raf = requestAnimationFrame(loop); };
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
    io.observe(canvas);
    resize();
    window.addEventListener('resize', resize);
    if (reduce) draw(); else loop();
    return () => { cancelAnimationFrame(raf); io.disconnect(); window.removeEventListener('resize', resize); };
  }, [reducedMotion]);
  return <canvas ref={ref} className="particle-wave" aria-hidden="true" />;
}
