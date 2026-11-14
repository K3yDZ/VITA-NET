// starfield.js — lightweight canvas star field, no dependencies.
// Density scales with screen area so it stays cheap on small/mobile
// screens. Respects prefers-reduced-motion by rendering static stars.

export function initStarfield(canvasId = "starfield") {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let stars = [];
  let dpr = Math.min(window.devicePixelRatio || 1, 2);

  function sizeCanvas() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    seedStars(w, h);
  }

  function seedStars(w, h) {
    const count = Math.round((w * h) / 3800); // density tuned for a busy-but-calm sky
    stars = new Array(count).fill(0).map(() => ({
      x: Math.random() * w,
      y: Math.random() * h,
      r: Math.random() * 1.3 + 0.2,
      phase: Math.random() * Math.PI * 2,
      speed: 0.6 + Math.random() * 1.2,
      baseAlpha: 0.35 + Math.random() * 0.65,
    }));
  }

  function draw(t) {
    const w = window.innerWidth;
    const h = window.innerHeight;
    ctx.clearRect(0, 0, w, h);
    for (const s of stars) {
      const twinkle = reduceMotion ? 1 : 0.55 + 0.45 * Math.sin(s.phase + t * 0.0011 * s.speed);
      ctx.globalAlpha = s.baseAlpha * twinkle;
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    if (!reduceMotion) requestAnimationFrame(draw);
  }

  sizeCanvas();
  window.addEventListener("resize", sizeCanvas);
  requestAnimationFrame(draw);
  if (reduceMotion) draw(0); // paint once, no loop
}
