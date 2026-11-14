// charts.js — a small canvas line-chart renderer.
//
// Deliberately not using a CDN chart library: at a hackathon, the venue
// wifi is the least reliable part of the system, and a chart is not worth
// a blank panel if a CDN request stalls mid-demo. This draws a line, a
// couple of gridlines, and one optional reference threshold line — which
// is all the trend view needs.

import { t } from "./i18n.js";

export function drawTrendChart(canvas, points, { unit = "", refLine = null, color = "#5fd4c8" } = {}) {
  if (!canvas) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const cssW = canvas.clientWidth || 300;
  const cssH = canvas.clientHeight || 160;
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const padding = { top: 10, right: 10, bottom: 18, left: 34 };
  const plotW = cssW - padding.left - padding.right;
  const plotH = cssH - padding.top - padding.bottom;

  if (!points || points.length < 2) {
    ctx.fillStyle = "#5b6c85";
    ctx.font = "12px sans-serif";
    ctx.fillText(t("collecting_data"), padding.left, cssH / 2);
    return;
  }

  const values = points.map((p) => p.v);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (refLine != null) {
    min = Math.min(min, refLine);
    max = Math.max(max, refLine);
  }
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.12;
  min -= pad;
  max += pad;

  const x = (i) => padding.left + (i / (points.length - 1)) * plotW;
  const y = (v) => padding.top + plotH - ((v - min) / (max - min)) * plotH;

  // gridlines
  ctx.strokeStyle = "#24344a";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 2; i++) {
    const gy = padding.top + (plotH / 2) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, gy);
    ctx.lineTo(cssW - padding.right, gy);
    ctx.stroke();
  }

  // reference threshold line
  if (refLine != null) {
    ctx.strokeStyle = "#ffcc4d";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(padding.left, y(refLine));
    ctx.lineTo(cssW - padding.right, y(refLine));
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // data line
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.75;
  ctx.beginPath();
  points.forEach((p, i) => {
    const px = x(i);
    const py = y(p.v);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();

  // latest-value dot
  const last = points.length - 1;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x(last), y(points[last].v), 2.6, 0, Math.PI * 2);
  ctx.fill();

  // axis labels
  ctx.fillStyle = "#5b6c85";
  ctx.font = "10px sans-serif";
  ctx.fillText(`${max.toFixed(0)}${unit}`, 2, padding.top + 8);
  ctx.fillText(`${min.toFixed(0)}${unit}`, 2, cssH - 4);
}

export function drawTrendChartMulti(canvas, seriesA, seriesB, opts={}){
  if(!seriesB || !seriesB.length) return drawTrendChart(canvas, seriesA, opts);
  // draw A solid, B dashed grey
  drawTrendChart(canvas, seriesA, opts);
  if(!canvas) return;
  const dpr=Math.min(window.devicePixelRatio||1,2);
  const cssW=canvas.clientWidth||300, cssH=canvas.clientHeight||160;
  // we already drew A, now overlay B dashed
  const ctx=canvas.getContext("2d");
  ctx.setTransform(dpr,0,0,dpr,0,0);
  const padding={top:10,right:10,bottom:18,left:34};
  const plotW=cssW-padding.left-padding.right, plotH=cssH-padding.top-padding.bottom;
  const all=[...seriesA.map(p=>p.v), ...seriesB.map(p=>p.v)];
  let min=Math.min(...all), max=Math.max(...all);
  if(opts.refLine!=null){ min=Math.min(min, opts.refLine); max=Math.max(max, opts.refLine); }
  if(min===max){min-=1; max+=1;}
  const pad=(max-min)*0.12; min-=pad; max+=pad;
  const x=(i, n)=> padding.left + (i/(n-1))*plotW;
  const y=(v)=> padding.top + plotH - ((v-min)/(max-min))*plotH;
  ctx.strokeStyle="#9aa8c0"; ctx.lineWidth=1.2; ctx.setLineDash([6,4]);
  ctx.beginPath();
  seriesB.forEach((p,i)=>{ const px=x(i, seriesB.length), py=y(p.v); if(i===0)ctx.moveTo(px,py); else ctx.lineTo(px,py); });
  ctx.stroke(); ctx.setLineDash([]);
}