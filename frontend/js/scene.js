/* scene.js — the low-poly counselling room, the three figures, and the
 * speech-bubble / "YOU" marker overlay. Degrades to available=false when the
 * Three.js CDN cannot be reached (ui.js then runs in plain text mode).
 */
const Scene = (() => {
  const COLORS = { client: 0x5aa9f2, counselor: 0x4fc38a, supervisor: 0xb184f0 };
  const SEAT_Y = 0.45;

  let renderer, scene, camera, canvas, overlay;
  let figures = {}, youMarker, youTarget = null, youFrom = null, youT = 1;
  let bubbles = {}, clock = 0, last = 0, raf = null;
  let azimuth = 0, polar = 0, dragging = false, lastX = 0, lastY = 0;
  let available = false;

  /* ------------------------- room ------------------------- */
  function lambert(color, opts) {
    return new THREE.MeshLambertMaterial(Object.assign({ color }, opts || {}));
  }
  function box(w, h, d, color, x, y, z, parent) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), lambert(color));
    m.position.set(x, y, z);
    m.castShadow = true; m.receiveShadow = true;
    (parent || scene).add(m);
    return m;
  }

  function buildSeat(kind, color) {
    const g = new THREE.Group();
    const w = kind === "sofa" ? 2.0 : 1.05;
    box(w, 0.36, 0.95, color, 0, 0.26, 0, g);                 // seat
    box(w, 0.75, 0.2, color, 0, 0.62, -0.5, g);               // back
    box(0.16, 0.42, 0.95, color, -w / 2 + 0.08, 0.6, 0, g);   // arms
    box(0.16, 0.42, 0.95, color, w / 2 - 0.08, 0.6, 0, g);
    [-1, 1].forEach((sx) => [-1, 1].forEach((sz) => {
      box(0.1, 0.16, 0.1, 0x4a3b2e, sx * (w / 2 - 0.12), 0.08, sz * 0.38, g);
    }));
    return g;
  }

  function buildPlant(x, z) {
    const g = new THREE.Group();
    const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.17, 0.32, 10), lambert(0xc4785a));
    pot.position.y = 0.16; pot.castShadow = true; g.add(pot);
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.05, 0.7, 6), lambert(0x4a7a3c));
    stem.position.y = 0.6; g.add(stem);
    [[0.0, 1.05, 0.34], [0.22, 0.86, 0.26], [-0.2, 0.92, 0.24]].forEach(([dx, y, r]) => {
      const leaf = new THREE.Mesh(new THREE.IcosahedronGeometry(r, 0), lambert(0x5f9a48));
      leaf.position.set(dx, y, dx * 0.4);
      leaf.castShadow = true;
      g.add(leaf);
    });
    g.position.set(x, 0, z);
    scene.add(g);
  }

  function buildRoom() {
    // floor + rug
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(16, 14),
      lambert(0x8a6547)
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    const rug = new THREE.Mesh(new THREE.CircleGeometry(2.6, 36), lambert(0xb5735f));
    rug.rotation.x = -Math.PI / 2;
    rug.position.set(0, 0.01, 0.5);
    rug.receiveShadow = true;
    scene.add(rug);

    // back + side walls
    box(16, 4, 0.2, 0xd9c3a5, 0, 2, -5.6);
    box(0.2, 4, 12, 0xcbb595, -7.4, 2, -0.6);
    box(0.2, 4, 12, 0xcbb595, 7.4, 2, -0.6);

    // one-way mirror wall separating the observation booth
    const glass = new THREE.Mesh(
      new THREE.PlaneGeometry(9, 2.7),
      new THREE.MeshLambertMaterial({
        color: 0xa9d6ea, transparent: true, opacity: 0.22, side: THREE.DoubleSide,
      })
    );
    glass.position.set(0, 1.55, -2.7);
    scene.add(glass);
    box(9.2, 0.14, 0.24, 0x6b5a48, 0, 2.95, -2.7);
    box(0.16, 2.9, 0.24, 0x6b5a48, -4.5, 1.5, -2.7);
    box(0.16, 2.9, 0.24, 0x6b5a48, 4.5, 1.5, -2.7);

    // observation booth floor + desk
    box(9, 0.3, 2.4, 0x7b6550, 0, 0.15, -3.95);
    box(2.2, 0.12, 0.7, 0x5d4a3a, 0, 0.92, -3.25);
    box(0.5, 0.35, 0.3, 0x2f2a38, -0.6, 1.15, -3.3);   // notes on the desk

    // coffee table + tissue box + mug
    box(1.35, 0.1, 0.7, 0x6b4f3a, 0, 0.44, 0.55);
    [[-0.55, 0.3], [0.55, 0.3], [-0.55, 0.8], [0.55, 0.8]].forEach(([x, z]) => {
      box(0.09, 0.44, 0.09, 0x4d3828, x, 0.22, z);
    });
    box(0.3, 0.2, 0.22, 0xf2f0ea, -0.3, 0.59, 0.55);   // tissue box
    box(0.12, 0.06, 0.1, 0xffffff, -0.3, 0.71, 0.55);  // tissue
    const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.07, 0.15, 12), lambert(0xe8e2d8));
    mug.position.set(0.35, 0.57, 0.55); mug.castShadow = true; scene.add(mug);

    buildPlant(2.9, -1.2);
    buildPlant(-3.1, -1.4);

    // floor lamp (warm)
    box(0.12, 1.8, 0.12, 0x3c3444, -2.7, 0.9, 0.9);
    const shade = new THREE.Mesh(new THREE.ConeGeometry(0.34, 0.4, 14, 1, true), lambert(0xf3d9a8, { side: THREE.DoubleSide }));
    shade.position.set(-2.7, 1.95, 0.9);
    scene.add(shade);

    // wall art (three blocks, echoes the three roles)
    box(0.5, 0.7, 0.06, COLORS.client, -1.2, 2.2, -5.45);
    box(0.5, 0.7, 0.06, COLORS.counselor, 0, 2.2, -5.45);
    box(0.5, 0.7, 0.06, COLORS.supervisor, 1.2, 2.2, -5.45);
  }

  function buildFigures() {
    const specs = {
      client: { x: -1.75, z: 0.45, rot: Math.PI * 0.22, seat: "sofa", seatColor: 0x7d6fb0 },
      counselor: { x: 1.75, z: 0.45, rot: -Math.PI * 0.22, seat: "chair", seatColor: 0x6f8f7d },
      supervisor: { x: 0, z: -3.9, rot: 0, seat: "chair", seatColor: 0x6a5c80, y: 0.3 },
    };
    Object.keys(specs).forEach((role) => {
      const s = specs[role];
      const seat = buildSeat(s.seat, s.seatColor);
      seat.position.set(s.x, s.y || 0, s.z);
      seat.rotation.y = s.rot;
      scene.add(seat);

      const f = Figures.createFigure({
        body: COLORS[role],
        skin: role === "client" ? 0xe8bd96 : role === "counselor" ? 0xf0cdad : 0xd7a882,
        accent: role === "supervisor" ? 0x3b2f52 : 0x3a3346,
        hair: role === "client" ? 0x3a2c22 : role === "counselor" ? 0x54301f : 0x22202e,
      });
      f.group.position.set(s.x, SEAT_Y + (s.y || 0), s.z + 0.05);
      f.group.rotation.y = s.rot;
      f.baseY = SEAT_Y + (s.y || 0);
      scene.add(f.group);
      figures[role] = f;
    });
  }

  /* ------------------------- YOU marker ------------------------- */
  function markerPos(role) {
    const f = figures[role];
    return new THREE.Vector3(f.group.position.x, f.baseY + 1.95, f.group.position.z);
  }

  let youRole = null;
  function setYou(role, instant) {
    if (!available) return;
    if (role === youRole && !instant) return;   // already there - don't re-animate
    youRole = role;
    Object.keys(figures).forEach((r) => figures[r].setHighlight(r === role));
    if (!youMarker) return;
    const target = markerPos(role);
    if (instant || !youTarget) {
      youMarker.position.copy(target);
      youTarget = target; youFrom = target.clone(); youT = 1;
    } else {
      youFrom = youMarker.position.clone();
      youTarget = target;
      youT = 0;               // animate over 0.5s in the render loop
    }
    youMarker.visible = true;
  }

  /* ------------------------- bubbles ------------------------- */
  function bubbleFor(role) {
    if (!bubbles[role]) {
      const el = document.createElement("div");
      el.className = "bubble " + role;
      el.style.display = "none";
      overlay.appendChild(el);
      bubbles[role] = el;
    }
    return bubbles[role];
  }

  function positionBubbles() {
    const rect = canvas.getBoundingClientRect();
    Object.keys(bubbles).forEach((role) => {
      const el = bubbles[role];
      if (el.style.display === "none") return;
      const f = figures[role];
      const v = new THREE.Vector3(
        f.group.position.x, f.baseY + 1.72, f.group.position.z
      ).project(camera);
      el.style.left = ((v.x * 0.5 + 0.5) * rect.width) + "px";
      el.style.top = ((-v.y * 0.5 + 0.5) * rect.height) + "px";
    });
  }

  function hideBubble(role) {
    if (bubbles[role]) bubbles[role].style.display = "none";
  }

  function clearBubbles() {
    Object.keys(bubbles).forEach(hideBubble);
    Object.keys(figures).forEach((r) => figures[r] && figures[r].setSpeaking(false));
  }

  function showThinking(role, on) {
    if (!available) return;
    const el = bubbleFor(role);
    if (!on) { el.style.display = "none"; return; }
    el.innerHTML = '<span class="who">' + role + '</span><span class="thinking-dots">'
      + '<span>.</span><span>.</span><span>.</span></span>';
    el.style.display = "block";
    positionBubbles();
  }

  let speakToken = 0;
  function speak(role, text, emotion) {
    if (!available) return Promise.resolve();
    const token = ++speakToken;
    const f = figures[role];
    f.setExpression(emotion || "neutral");
    f.setSpeaking(true);
    const el = bubbleFor(role);
    el.style.display = "block";
    el.innerHTML = '<span class="who">' + role + '</span><span class="txt"></span>';
    const txt = el.querySelector(".txt");
    const chars = Array.from(text);
    const step = Math.max(10, Math.min(38, 1800 / Math.max(chars.length, 1)));

    return new Promise((resolve) => {
      let i = 0;
      (function tick() {
        if (token !== speakToken) return resolve();
        txt.textContent = chars.slice(0, ++i).join("");
        positionBubbles();
        if (i < chars.length) setTimeout(tick, step);
        else {
          f.setSpeaking(false);
          setTimeout(() => {
            if (token === speakToken) el.style.display = "none";
            resolve();
          }, 1400);
        }
      })();
    });
  }

  function setExpression(role, emotion) {
    if (available && figures[role]) figures[role].setExpression(emotion);
  }

  /* ------------------------- loop ------------------------- */
  function resize() {
    if (!available) return;
    const rect = canvas.parentElement.getBoundingClientRect();
    const w = Math.max(rect.width, 1), h = Math.max(rect.height, 1);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  function frame(now) {
    raf = requestAnimationFrame(frame);
    const dt = Math.min(0.05, (now - last) / 1000 || 0.016);
    last = now; clock += dt;

    Object.keys(figures).forEach((r) => figures[r].update(dt));

    if (youMarker && youT < 1) {
      youT = Math.min(1, youT + dt / 0.5);
      const e = youT < 0.5 ? 2 * youT * youT : -1 + (4 - 2 * youT) * youT;  // ease in-out
      youMarker.position.lerpVectors(youFrom, youTarget, e);
      youMarker.position.y += Math.sin(Math.PI * youT) * 0.6;              // little arc
    } else if (youMarker && youTarget) {
      youMarker.position.y = youTarget.y + Math.sin(clock * 2.2) * 0.07;
    }

    const radius = 7.4, height = 4.3;
    camera.position.set(
      Math.sin(azimuth) * radius,
      height + polar,
      Math.cos(azimuth) * radius
    );
    camera.lookAt(0, 1.1, -0.4);

    positionBubbles();
    renderer.render(scene, camera);
  }

  /* ------------------------- init ------------------------- */
  function init(canvasEl, overlayEl) {
    canvas = canvasEl; overlay = overlayEl;
    if (typeof THREE === "undefined") { available = false; return false; }
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    } catch (e) {
      available = false;
      return false;
    }
    available = true;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x2a2030);
    scene.fog = new THREE.Fog(0x2a2030, 14, 24);

    camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);

    scene.add(new THREE.HemisphereLight(0xffe6c4, 0x40303a, 0.75));
    const key = new THREE.DirectionalLight(0xffd9a8, 0.85);
    key.position.set(4.5, 8, 5.5);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.left = -9; key.shadow.camera.right = 9;
    key.shadow.camera.top = 9; key.shadow.camera.bottom = -9;
    scene.add(key);
    const warm = new THREE.PointLight(0xffb974, 0.7, 12);
    warm.position.set(-2.7, 2.1, 0.9);
    scene.add(warm);
    const fill = new THREE.PointLight(0x9fb8ff, 0.35, 16);
    fill.position.set(0, 3, -3.6);
    scene.add(fill);

    buildRoom();
    buildFigures();

    youMarker = Figures.labelSprite("YOU", "#ffd97a");
    youMarker.visible = false;
    scene.add(youMarker);

    // simple drag-to-orbit (no external controls dependency)
    canvas.addEventListener("pointerdown", (e) => {
      dragging = true; lastX = e.clientX; lastY = e.clientY;
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      azimuth = Math.max(-0.75, Math.min(0.75, azimuth - (e.clientX - lastX) * 0.005));
      polar = Math.max(-1.2, Math.min(2.4, polar + (e.clientY - lastY) * 0.012));
      lastX = e.clientX; lastY = e.clientY;
    });
    const stop = () => { dragging = false; };
    canvas.addEventListener("pointerup", stop);
    canvas.addEventListener("pointerleave", stop);

    window.addEventListener("resize", resize);
    resize();
    if (raf) cancelAnimationFrame(raf);
    last = performance.now();
    raf = requestAnimationFrame(frame);
    return true;
  }

  return {
    init, resize, setYou, speak, showThinking, setExpression, clearBubbles,
    get available() { return available; },
  };
})();
