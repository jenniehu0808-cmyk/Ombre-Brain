// Headless three.js renderer for STL parts.
// usage: node render.js --out <dir> --prefix <name> [--views top,side,iso,front] [--size 1024] part.stl[:#hex] ...
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.PW_CORE || '/tmp/claude-0/-home-user-Ombre-Brain/9002accb-7049-5992-a1b1-8c5fa84f722b/scratchpad/pw/node_modules/playwright-core');
const THREE_DIR = process.env.THREE_DIR || '/tmp/claude-0/-home-user-Ombre-Brain/9002accb-7049-5992-a1b1-8c5fa84f722b/scratchpad/pw/node_modules/three';
const CHROME = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

const args = process.argv.slice(2);
let out = '.', prefix = 'render', views = ['top', 'side', 'iso', 'front'], size = 1024, bg = '#0b0b0b';
const parts = [];
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === '--out') out = args[++i];
  else if (a === '--prefix') prefix = args[++i];
  else if (a === '--views') views = args[++i].split(',');
  else if (a === '--size') size = parseInt(args[++i]);
  else if (a === '--bg') bg = args[++i];
  else {
    const [file, color] = a.split(':#');
    parts.push({ url: 'file://' + path.resolve(file), color: color ? '#' + color : '#f1ebdc' });
  }
}
if (!parts.length) { console.error('no parts'); process.exit(1); }

const html = `<!doctype html><html><head><meta charset="utf-8">
<script type="importmap">{"imports":{"three":"file://${THREE_DIR}/build/three.module.js","three/addons/":"file://${THREE_DIR}/examples/jsm/"}}</script>
<style>body{margin:0;background:${bg}}canvas{display:block}</style></head><body>
<script type="module">
import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import * as BGU from 'three/addons/utils/BufferGeometryUtils.js';
const renderer = new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
renderer.setPixelRatio(1); renderer.setSize(${size}, ${size});
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color('${bg}');
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(40, -60, 120); key.castShadow = true;
key.shadow.mapSize.set(2048, 2048); key.shadow.radius = 6; key.shadow.bias = -0.0005; scene.add(key);
const fill = new THREE.DirectionalLight(0xdde6ff, 0.7); fill.position.set(-80, 40, 60); scene.add(fill);
const rim = new THREE.DirectionalLight(0xffffff, 1.2); rim.position.set(0, 80, -40); scene.add(rim);
scene.add(new THREE.AmbientLight(0xffffff, 0.25));
const group = new THREE.Group(); scene.add(group);
const loader = new STLLoader();
const parts = ${JSON.stringify(parts)};
window.__ready = false;
let loaded = 0;
for (const p of parts) {
  loader.load(p.url, geo0 => {
    geo0.deleteAttribute('normal');
    const geo = BGU.mergeVertices(geo0, 1e-4);
    geo.computeVertexNormals();
    const dark = (parseInt(p.color.slice(1),16) & 0xff) < 0x60;
    const mat = new THREE.MeshPhysicalMaterial({color: p.color, roughness: dark ? 0.35 : 0.42, metalness: dark ? 0.15 : 0.0, clearcoat: dark ? 0.6 : 0.25, clearcoatRoughness: 0.3, side: THREE.DoubleSide});
    const mesh = new THREE.Mesh(geo, mat); mesh.castShadow = true; mesh.receiveShadow = true; group.add(mesh);
    if (++loaded === parts.length) window.__ready = true;
  }, undefined, err => { window.__error = String(err); });
}
let ground = null;
window.renderView = (view) => {
  const box = new THREE.Box3().setFromObject(group);
  if (!ground) {
    const gr = box.getBoundingSphere(new THREE.Sphere()).radius;
    ground = new THREE.Mesh(new THREE.PlaneGeometry(gr * 8, gr * 8), new THREE.ShadowMaterial({ opacity: 0.35 }));
    ground.position.set(0, 0, box.min.z - 0.2); ground.receiveShadow = true; scene.add(ground);
    const sc = key.shadow.camera; sc.left = -gr * 2; sc.right = gr * 2; sc.top = gr * 2; sc.bottom = -gr * 2; sc.near = 1; sc.far = gr * 10;
    key.target.position.copy(box.getCenter(new THREE.Vector3())); scene.add(key.target); sc.updateProjectionMatrix();
  }
  ground.visible = !(view === 'top' || view === 'under');
  const sph = box.getBoundingSphere(new THREE.Sphere());
  const c = sph.center, r = sph.radius;
  const cam = new THREE.PerspectiveCamera(32, 1, 1, 5000);
  cam.up.set(0, 0, 1);
  const d = r * 3.4;
  const dirs = {
    top:   [0, -0.0001, 1],
    side:  [1, -1.3, 0.55],
    iso:   [1, -1, 1.1],
    front: [0, -1, 0.25],
    under: [0.6, -1, -0.8],
    side2: [-1.2, -1, 0.45],
  };
  let v = dirs[view] || dirs.iso;
  if (view.startsWith('az')) { // az<deg>_el<deg>
    const m = view.match(/az(-?\\d+)_el(-?\\d+)/); const az = m[1]*Math.PI/180, el = m[2]*Math.PI/180;
    v = [Math.cos(el)*Math.cos(az), Math.cos(el)*Math.sin(az), Math.sin(el)];
  }
  const n = Math.hypot(...v);
  cam.position.set(c.x + v[0]/n*d, c.y + v[1]/n*d, c.z + v[2]/n*d);
  cam.lookAt(c);
  cam.updateProjectionMatrix();
  renderer.render(scene, cam);
  return renderer.domElement.toDataURL('image/png');
};
</script></body></html>`;

(async () => {
  const htmlPath = path.join(out, `.${prefix}_viewer.html`);
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(htmlPath, html);
  const browser = await chromium.launch({
    executablePath: CHROME,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--allow-file-access-from-files', '--no-sandbox', '--disable-web-security'],
  });
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  page.on('console', m => { if (m.type() === 'error') console.error('[page]', m.text()); });
  page.on('pageerror', e => console.error('[pageerror]', e.message));
  await page.goto('file://' + path.resolve(htmlPath));
  await page.waitForFunction(() => window.__ready || window.__error, null, { timeout: 120000 });
  const err = await page.evaluate(() => window.__error);
  if (err) { console.error('load error', err); process.exit(2); }
  for (const v of views) {
    const dataUrl = await page.evaluate(v => window.renderView(v), v);
    const buf = Buffer.from(dataUrl.split(',')[1], 'base64');
    const f = path.join(out, `${prefix}_${v}.png`);
    fs.writeFileSync(f, buf);
    console.log('wrote', f);
  }
  await browser.close();
  fs.unlinkSync(htmlPath);
})().catch(e => { console.error(e); process.exit(1); });
