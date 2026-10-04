/* figures.js — original blocky toy-figure characters.
 *
 * Design note: these are an original "wooden block toy" design made from
 * primitives (rounded cylinder head with a knob, chamfered block torso,
 * C-shaped hands, separate block legs). No third-party toy branding, naming
 * or official figure shape is used or reproduced.
 */
const Figures = (() => {
  const EXPRESSIONS = ["neutral", "sad", "anxious", "angry", "relieved", "thinking"];
  const faceCache = {};

  /* ---------------- face textures ---------------- */
  function drawFace(expr) {
    const c = document.createElement("canvas");
    c.width = c.height = 256;
    const g = c.getContext("2d");
    g.clearRect(0, 0, 256, 256);
    g.lineCap = "round";
    g.lineJoin = "round";
    const ink = "#241c2e";
    g.strokeStyle = ink;
    g.fillStyle = ink;

    const eye = (x, y, r) => { g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); };
    const brow = (x, y, tilt, len) => {
      g.lineWidth = 11;
      g.beginPath();
      g.moveTo(x - len, y + tilt);
      g.lineTo(x + len, y - tilt);
      g.stroke();
    };
    const mouth = (path) => { g.lineWidth = 11; g.beginPath(); path(); g.stroke(); };

    switch (expr) {
      case "sad":
        brow(84, 96, -8, 24); brow(172, 96, 8, 24);
        eye(84, 124, 13); eye(172, 124, 13);
        mouth(() => g.arc(128, 208, 34, Math.PI * 1.15, Math.PI * 1.85));
        break;
      case "anxious":
        brow(84, 92, -12, 26); brow(172, 92, 12, 26);
        eye(84, 126, 15); eye(172, 126, 15);
        mouth(() => {          // wavy line
          g.moveTo(96, 188);
          g.quadraticCurveTo(112, 176, 128, 188);
          g.quadraticCurveTo(144, 200, 160, 188);
        });
        g.beginPath();         // sweat drop
        g.fillStyle = "#7fc4e8";
        g.moveTo(206, 92); g.quadraticCurveTo(220, 118, 206, 126);
        g.quadraticCurveTo(192, 118, 206, 92); g.fill();
        g.fillStyle = ink;
        break;
      case "angry":
        brow(84, 100, 14, 28); brow(172, 100, -14, 28);
        eye(84, 132, 13); eye(172, 132, 13);
        mouth(() => { g.moveTo(96, 194); g.lineTo(160, 194); });
        break;
      case "relieved":
        g.lineWidth = 11;      // closed happy eyes
        g.beginPath(); g.arc(84, 132, 20, Math.PI * 1.1, Math.PI * 1.9); g.stroke();
        g.beginPath(); g.arc(172, 132, 20, Math.PI * 1.1, Math.PI * 1.9); g.stroke();
        mouth(() => g.arc(128, 172, 34, Math.PI * 0.18, Math.PI * 0.82));
        break;
      case "thinking":
        brow(84, 94, 4, 24); brow(176, 84, 10, 22);
        eye(84, 126, 13); eye(172, 126, 11);
        mouth(() => { g.moveTo(104, 194); g.lineTo(148, 186); });
        g.beginPath(); g.arc(196, 204, 7, 0, 6.3); g.fill();
        g.beginPath(); g.arc(214, 190, 4, 0, 6.3); g.fill();
        break;
      default:                 // neutral
        eye(84, 124, 14); eye(172, 124, 14);
        mouth(() => { g.moveTo(102, 188); g.lineTo(154, 188); });
    }

    const tex = new THREE.CanvasTexture(c);
    tex.anisotropy = 4;
    return tex;
  }

  function faceTexture(expr) {
    if (!faceCache[expr]) faceCache[expr] = drawFace(expr);
    return faceCache[expr];
  }

  function labelSprite(text, color) {
    const c = document.createElement("canvas");
    c.width = 256; c.height = 128;
    const g = c.getContext("2d");
    g.font = "bold 78px Segoe UI, sans-serif";
    g.textAlign = "center"; g.textBaseline = "middle";
    g.shadowColor = color; g.shadowBlur = 26;
    g.fillStyle = "#ffffff";
    g.fillText(text, 128, 66);
    g.fillText(text, 128, 66);
    const tex = new THREE.CanvasTexture(c);
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
    const sp = new THREE.Sprite(mat);
    sp.scale.set(0.85, 0.42, 1);
    return sp;
  }

  /* ---------------- figure ---------------- */
  function mat(color, opts) {
    return new THREE.MeshLambertMaterial(Object.assign({ color }, opts || {}));
  }

  function block(w, h, d, color) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color));
    m.castShadow = true;
    return m;
  }

  /**
   * Build a seated blocky figure.
   * @param {object} o  {body, head, skin, accent}
   */
  function createFigure(o) {
    const skin = o.skin || 0xf0c9a4;
    const body = o.body;
    const accent = o.accent || 0x2d2438;

    const group = new THREE.Group();

    // hips + legs (seated pose: thighs forward, shins down)
    const hips = block(0.62, 0.22, 0.44, accent);
    hips.position.y = 0.11;
    group.add(hips);

    [-0.17, 0.17].forEach((x) => {
      const thigh = block(0.22, 0.2, 0.46, accent);
      thigh.position.set(x, 0.12, 0.27);
      group.add(thigh);
      const shin = block(0.2, 0.42, 0.2, accent);
      shin.position.set(x, -0.1, 0.45);
      group.add(shin);
      const foot = block(0.22, 0.1, 0.3, 0x35303f);
      foot.position.set(x, -0.33, 0.52);
      group.add(foot);
    });

    // torso — block with a chamfered bib on top
    const torso = block(0.6, 0.62, 0.42, body);
    torso.position.y = 0.53;
    group.add(torso);

    const bib = new THREE.Mesh(
      new THREE.CylinderGeometry(0.3, 0.34, 0.16, 4),
      mat(body)
    );
    bib.rotation.y = Math.PI / 4;
    bib.position.y = 0.88;
    bib.castShadow = true;
    group.add(bib);

    // arms: shoulder pivots, forearms resting forward, C-shaped hands
    const arms = [];
    [-1, 1].forEach((side) => {
      const pivot = new THREE.Group();
      pivot.position.set(side * 0.36, 0.78, 0);
      const upper = block(0.17, 0.4, 0.19, body);
      upper.position.y = -0.2;
      pivot.add(upper);

      const fore = new THREE.Group();
      fore.position.y = -0.4;
      const foreMesh = block(0.16, 0.34, 0.18, body);
      foreMesh.position.y = -0.17;
      fore.add(foreMesh);

      const hand = new THREE.Mesh(
        new THREE.TorusGeometry(0.1, 0.045, 8, 14, Math.PI * 1.45),
        mat(skin)
      );
      hand.castShadow = true;
      hand.position.y = -0.4;
      hand.rotation.set(Math.PI / 2, 0, Math.PI * 0.15);
      fore.add(hand);

      fore.rotation.x = -1.15;      // forearm forward onto the lap
      pivot.add(fore);
      pivot.rotation.x = 0.12;
      group.add(pivot);
      arms.push(pivot);
    });

    // neck + head
    const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.12, 12), mat(skin));
    neck.position.y = 0.92;
    group.add(neck);

    const head = new THREE.Group();
    head.position.y = 1.22;
    const skull = new THREE.Mesh(new THREE.CylinderGeometry(0.33, 0.33, 0.46, 26), mat(skin));
    skull.castShadow = true;
    head.add(skull);

    const knob = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.12, 0.09, 16), mat(skin));
    knob.position.y = 0.27;
    head.add(knob);

    const hair = new THREE.Mesh(new THREE.CylinderGeometry(0.345, 0.345, 0.14, 26), mat(o.hair || accent));
    hair.position.y = 0.17;
    head.add(hair);

    const faceMat = new THREE.MeshBasicMaterial({
      map: faceTexture("neutral"), transparent: true,
    });
    const face = new THREE.Mesh(new THREE.PlaneGeometry(0.52, 0.44), faceMat);
    face.position.set(0, 0.01, 0.332);
    head.add(face);
    group.add(head);

    // feet-level highlight ring (shown only for the role the user controls)
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.46, 0.62, 36),
      new THREE.MeshBasicMaterial({ color: 0xffe9a8, transparent: true, opacity: 0.0, side: THREE.DoubleSide })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = -0.38;
    group.add(ring);

    const api = {
      group, head, face, ring, arms,
      expression: "neutral",
      speaking: false,
      _t: Math.random() * 6,
      baseY: 0,
      setExpression(expr) {
        if (!EXPRESSIONS.includes(expr)) expr = "neutral";
        api.expression = expr;
        faceMat.map = faceTexture(expr);
        faceMat.needsUpdate = true;
      },
      setSpeaking(on) { api.speaking = !!on; },
      setHighlight(on) { ring.material.opacity = on ? 0.55 : 0.0; },
      update(dt) {
        api._t += dt;
        if (api.speaking) {
          group.position.y = api.baseY + Math.abs(Math.sin(api._t * 7)) * 0.055;
          head.rotation.z = Math.sin(api._t * 3.5) * 0.045;
        } else {
          // idle breathing
          group.position.y = api.baseY + Math.sin(api._t * 1.4) * 0.012;
          head.rotation.z *= 0.9;
        }
        if (ring.material.opacity > 0) {
          ring.material.opacity = 0.42 + Math.sin(api._t * 2.4) * 0.16;
        }
      },
    };
    return api;
  }

  return { createFigure, labelSprite, faceTexture, EXPRESSIONS };
})();
