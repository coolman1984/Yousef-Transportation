// The studio clock: one offset (seconds) shared by the office program, the mailbox and every browser page.
import { writeFileSync } from 'node:fs';

export class StudioClock {
  constructor(file, startIso) {
    this.file = file;
    this.offset = (Date.parse(startIso) - Date.now()) / 1000;
    this.write();
    this.pages = [];
  }
  write() { writeFileSync(this.file, JSON.stringify({ offset: this.offset })); }
  now() { return new Date(Date.now() + this.offset * 1000); }
  /** script that makes the page's Date follow the studio clock (installed before the page's own scripts run) */
  initScript() {
    return `(() => {
      window.__studioOffset = ${this.offset * 1000};
      const R = Date;
      function D(...a) { if (!new.target) return new R(R.now() + window.__studioOffset).toString(); return a.length ? new R(...a) : new R(R.now() + window.__studioOffset); }
      D.prototype = R.prototype; D.now = () => R.now() + window.__studioOffset; D.UTC = R.UTC; D.parse = R.parse;
      Object.setPrototypeOf(D, R);
      window.Date = D;
    })();`;
  }
  attach(page) { this.pages.push(page); }
  /** move the studio clock forward (e.g. the drive between start and end) - everywhere at once */
  async jump(seconds) {
    this.offset += seconds;
    this.write();
    for (const p of this.pages) { try { await p.evaluate((ms) => { window.__studioOffset = ms; }, this.offset * 1000); } catch { /* page gone */ } }
    await new Promise((r) => setTimeout(r, 1200));     // the office and the mailbox re-read the file
  }
}

/** the phone's camera: a drawn odometer test image (the film says so), fed as a live camera stream */
export function fakeCameraScript() {
  return `(() => {
    window.__odo = window.__odo || '000000';
    const c = document.createElement('canvas'); c.width = 1280; c.height = 960;
    const g = c.getContext('2d');
    function paper() {
      g.fillStyle = '#5b4a3a'; g.fillRect(0, 0, 1280, 960);
      g.save(); g.translate(640, 480); g.rotate(-0.03);
      g.fillStyle = '#fbfaf6'; g.fillRect(-380, -440, 760, 880);
      g.fillStyle = '#222'; g.font = 'bold 34px sans-serif'; g.textAlign = 'center'; g.fillText('أمر تشغيل سيارة', 0, -380);
      g.strokeStyle = '#9aa0a6'; g.lineWidth = 2;
      for (let i = 0; i < 11; i++) { g.strokeRect(-340, -330 + i * 58, 680, 58); g.beginPath(); g.moveTo(-60, -330 + i * 58); g.lineTo(-60, -272 + i * 58); g.stroke(); }
      g.strokeStyle = '#1d3f8f'; g.lineWidth = 4; g.beginPath();
      for (let k = 0; k < 2; k++) { const y = 300 + k * 0; const x0 = k ? 60 : -300; g.moveTo(x0, y); for (let j = 1; j < 30; j++) g.lineTo(x0 + j * 8, y + Math.sin(j * 1.3 + k) * 14); }
      g.stroke(); g.restore();
      g.font = '22px sans-serif'; g.fillStyle = 'rgba(255,255,255,.6)'; g.textAlign = 'center'; g.fillText('TEST IMAGE · صورة تجريبية', 640, 940);
    }
    function draw() {
      if (window.__odo === 'paper') { paper(); requestAnimationFrame(draw); return; }
      const v = String(window.__odo).padStart(6, '0');
      const grd = g.createRadialGradient(640, 480, 60, 640, 480, 760); grd.addColorStop(0, '#2b2f36'); grd.addColorStop(1, '#0c0d10');
      g.fillStyle = grd; g.fillRect(0, 0, 1280, 960);
      g.strokeStyle = '#4a515c'; g.lineWidth = 14; g.beginPath(); g.arc(640, 470, 330, Math.PI * 0.8, Math.PI * 2.2); g.stroke();
      for (let i = 0; i <= 12; i++) { const a = Math.PI * 0.8 + i * (Math.PI * 1.4 / 12); g.strokeStyle = '#c9ced6'; g.lineWidth = 6;
        g.beginPath(); g.moveTo(640 + Math.cos(a) * 300, 470 + Math.sin(a) * 300); g.lineTo(640 + Math.cos(a) * 270, 470 + Math.sin(a) * 270); g.stroke(); }
      g.strokeStyle = '#ff6a3d'; g.lineWidth = 10; g.beginPath(); g.moveTo(640, 470); g.lineTo(640 + Math.cos(Math.PI * 1.35) * 250, 470 + Math.sin(Math.PI * 1.35) * 250); g.stroke();
      g.fillStyle = '#000'; g.fillRect(400, 560, 480, 110); g.strokeStyle = '#6b7280'; g.lineWidth = 4; g.strokeRect(400, 560, 480, 110);
      g.font = 'bold 86px monospace'; g.textAlign = 'center'; g.textBaseline = 'middle';
      for (let i = 0; i < 6; i++) { g.fillStyle = i % 2 ? '#141414' : '#1d1d1d'; g.fillRect(408 + i * 78, 568, 74, 94); g.fillStyle = '#f5f5f5'; g.fillText(v[i], 445 + i * 78, 617); }
      g.font = '28px sans-serif'; g.fillStyle = '#9aa3af'; g.fillText('km', 640, 700);
      g.font = '22px sans-serif'; g.fillStyle = 'rgba(255,255,255,.45)'; g.fillText('TEST IMAGE · صورة تجريبية', 640, 900);
      requestAnimationFrame(draw);
    }
    draw();
    const stream = c.captureStream(30);
    navigator.mediaDevices.getUserMedia = async () => stream.clone();
  })();`;
}
