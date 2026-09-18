<script>
  import { onMount } from "svelte";
  import { select } from "d3-selection";
  import { zoom as d3zoom, zoomIdentity } from "d3-zoom";
  import { isFlaggedUnsafe } from "./filterAndSort.js";

  let {
    items,
    selectedItem = $bindable(null),
    highlightedId,
    blurUnsafe,
  } = $props();

  const WORLD_SIZE = 2500;
  const BASE_TILE_SIZE = 10;
  const MAX_TILE_SIZE = 80;
  const MIN_ZOOM = 1;
  const MAX_ZOOM = 90;

  function currentTileSize() {
    return Math.min(MAX_TILE_SIZE, BASE_TILE_SIZE * transform.k);
  }

  let container = $state(null);
  let canvasEl = $state(null);
  let atlasError = $state(false);
  let unsupported = $state(false);

  let transform = zoomIdentity;
  let zoomBehavior;

  let gl = null;
  let program, vao;
  let atlasTex, atlasBlurredTex;
  let posBuffer, uvBuffer, unsafeBuffer;
  let uK, uTranslate, uResolution, uTileSizeLoc, uCellUVSizeLoc;
  let uAtlasLoc, uAtlasBlurredLoc, uBlurUnsafeLoc;
  let instanceCount = 0;
  let atlasCols = 0;
  let atlasCellUVSize = 0;

  const withCoords = $derived(
    items.filter((item) => item.x !== undefined && item.y !== undefined),
  );
  // Only entries the atlas actually has a thumbnail for get drawn — an
  // entry downloaded after the last `--build-atlas` run has coordinates
  // but no `atlasCell` yet, so it'd otherwise sample whatever happens to
  // be in atlas cell (0,0).
  const renderable = $derived(
    withCoords.filter((item) => item.atlasCell !== undefined),
  );

  const VERTEX_SRC = `#version 300 es
layout(location=0) in vec2 aCorner;
layout(location=1) in vec2 aInstancePos;
layout(location=2) in vec2 aInstanceUV;
layout(location=3) in float aInstanceUnsafe;

uniform float uK;
uniform vec2 uTranslate;
uniform vec2 uResolution;
uniform float uTileSize;
uniform float uCellUVSize;

out vec2 vUv;
out float vIsUnsafe;

void main() {
  vec2 screenPos = aInstancePos * uK + uTranslate;
  vec2 pixelPos = screenPos + aCorner * uTileSize;
  vec2 clip = (pixelPos / uResolution) * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  vUv = aInstanceUV + (aCorner + 0.5) * uCellUVSize;
  vIsUnsafe = aInstanceUnsafe;
}
`;

  const FRAGMENT_SRC = `#version 300 es
precision mediump float;
in vec2 vUv;
in float vIsUnsafe;
uniform sampler2D uAtlas;
uniform sampler2D uAtlasBlurred;
uniform float uBlurUnsafe;
out vec4 fragColor;

void main() {
  vec4 normalColor = texture(uAtlas, vUv);
  vec4 blurredColor = texture(uAtlasBlurred, vUv);
  float useBlur = (vIsUnsafe > 0.5 && uBlurUnsafe > 0.5) ? 1.0 : 0.0;
  fragColor = mix(normalColor, blurredColor, useBlur);
}
`;

  function compileShader(type, src) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, src);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const info = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error(`Shader compile error: ${info}`);
    }
    return shader;
  }

  function initGL() {
    gl = canvasEl.getContext("webgl2");
    if (!gl) {
      unsupported = true;
      return false;
    }

    const vs = compileShader(gl.VERTEX_SHADER, VERTEX_SRC);
    const fs = compileShader(gl.FRAGMENT_SHADER, FRAGMENT_SRC);
    program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(`Program link error: ${gl.getProgramInfoLog(program)}`);
    }

    uK = gl.getUniformLocation(program, "uK");
    uTranslate = gl.getUniformLocation(program, "uTranslate");
    uResolution = gl.getUniformLocation(program, "uResolution");
    uTileSizeLoc = gl.getUniformLocation(program, "uTileSize");
    uCellUVSizeLoc = gl.getUniformLocation(program, "uCellUVSize");
    uAtlasLoc = gl.getUniformLocation(program, "uAtlas");
    uAtlasBlurredLoc = gl.getUniformLocation(program, "uAtlasBlurred");
    uBlurUnsafeLoc = gl.getUniformLocation(program, "uBlurUnsafe");

    vao = gl.createVertexArray();
    gl.bindVertexArray(vao);

    const quad = new Float32Array([
      -0.5, -0.5, 0.5, -0.5, 0.5, 0.5, -0.5, -0.5, 0.5, 0.5, -0.5, 0.5,
    ]);
    const quadBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, quad, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    posBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuffer);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(1, 1);

    uvBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, uvBuffer);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 2, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(2, 1);

    unsafeBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, unsafeBuffer);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 1, gl.FLOAT, false, 0, 0);
    gl.vertexAttribDivisor(3, 1);

    gl.bindVertexArray(null);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    return true;
  }

  function uploadTexture(img) {
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
    gl.texParameteri(
      gl.TEXTURE_2D,
      gl.TEXTURE_MIN_FILTER,
      gl.LINEAR_MIPMAP_LINEAR,
    );
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.generateMipmap(gl.TEXTURE_2D);
    return tex;
  }

  async function loadAtlas() {
    try {
      const base = import.meta.env.BASE_URL;
      const metaRes = await fetch(`${base}data/atlas-meta.json`);
      if (!metaRes.ok) throw new Error(`HTTP ${metaRes.status}`);
      const meta = await metaRes.json();
      atlasCols = meta.cols;
      atlasCellUVSize = 1 / meta.cols; // cellSize / (cols * cellSize)

      const loadImg = (src) =>
        new Promise((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve(img);
          img.onerror = reject;
          img.src = src;
        });

      const [img, blurredImg] = await Promise.all([
        loadImg(`${base}data/atlas.jpg`),
        loadImg(`${base}data/atlas-blurred.jpg`),
      ]);
      atlasTex = uploadTexture(img);
      atlasBlurredTex = uploadTexture(blurredImg);
      rebuildInstances();
      render();
    } catch (err) {
      atlasError = true;
    }
  }

  function rebuildInstances() {
    if (!gl || !atlasTex) return;
    const n = renderable.length;
    const positions = new Float32Array(n * 2);
    const uvs = new Float32Array(n * 2);
    const unsafeFlags = new Float32Array(n);

    renderable.forEach((item, i) => {
      positions[i * 2] = item.x * WORLD_SIZE;
      positions[i * 2 + 1] = item.y * WORLD_SIZE;
      const col = item.atlasCell % atlasCols;
      const row = Math.floor(item.atlasCell / atlasCols);
      uvs[i * 2] = col * atlasCellUVSize;
      uvs[i * 2 + 1] = row * atlasCellUVSize;
      unsafeFlags[i] = isFlaggedUnsafe(item) ? 1 : 0;
    });

    gl.bindBuffer(gl.ARRAY_BUFFER, posBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.DYNAMIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, uvBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, uvs, gl.DYNAMIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, unsafeBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, unsafeFlags, gl.DYNAMIC_DRAW);

    instanceCount = n;
    render();
  }

  function render() {
    if (!gl || !canvasEl || !atlasTex) return;
    gl.viewport(0, 0, canvasEl.width, canvasEl.height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.useProgram(program);
    gl.bindVertexArray(vao);
    gl.uniform1f(uK, transform.k);
    gl.uniform2f(uTranslate, transform.x, transform.y);
    gl.uniform2f(uResolution, canvasEl.width, canvasEl.height);
    gl.uniform1f(uTileSizeLoc, currentTileSize());
    gl.uniform1f(uCellUVSizeLoc, atlasCellUVSize);
    gl.uniform1f(uBlurUnsafeLoc, blurUnsafe ? 1 : 0);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, atlasTex);
    gl.uniform1i(uAtlasLoc, 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, atlasBlurredTex);
    gl.uniform1i(uAtlasBlurredLoc, 1);

    if (instanceCount > 0) {
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, instanceCount);
    }
  }

  let renderScheduled = false;
  function scheduleRender() {
    if (renderScheduled) return;
    renderScheduled = true;
    requestAnimationFrame(() => {
      renderScheduled = false;
      render();
    });
  }

  function resizeCanvas() {
    if (!container || !canvasEl) return;
    canvasEl.width = container.clientWidth;
    canvasEl.height = container.clientHeight;
    render();
  }

  $effect(() => {
    renderable;
    rebuildInstances();
  });

  $effect(() => {
    blurUnsafe;
    highlightedId;
    scheduleRender();
  });

  function percentile(sortedValues, p) {
    const idx = (p / 100) * (sortedValues.length - 1);
    const lo = Math.floor(idx);
    const hi = Math.ceil(idx);
    if (lo === hi) return sortedValues[lo];
    return (
      sortedValues[lo] + (sortedValues[hi] - sortedValues[lo]) * (idx - lo)
    );
  }

  function fitToCluster() {
    if (withCoords.length === 0 || !container || !canvasEl || !zoomBehavior)
      return;
    const xs = withCoords.map((item) => item.x).sort((a, b) => a - b);
    const ys = withCoords.map((item) => item.y).sort((a, b) => a - b);
    const clusterWidth =
      Math.max(0.02, percentile(xs, 95) - percentile(xs, 5)) * WORLD_SIZE;
    const clusterHeight =
      Math.max(0.02, percentile(ys, 95) - percentile(ys, 5)) * WORLD_SIZE;
    const medianX = percentile(xs, 50) * WORLD_SIZE;
    const medianY = percentile(ys, 50) * WORLD_SIZE;

    const { clientWidth, clientHeight } = container;
    const k = Math.max(
      MIN_ZOOM,
      Math.min(
        MAX_ZOOM,
        Math.min(clientWidth / clusterWidth, clientHeight / clusterHeight) *
          0.95,
      ),
    );
    const next = zoomIdentity
      .translate(clientWidth / 2 - medianX * k, clientHeight / 2 - medianY * k)
      .scale(k);
    select(canvasEl).call(zoomBehavior.transform, next);
  }

  function onCanvasClick(e) {
    const rect = canvasEl.getBoundingClientRect();
    const [worldX, worldY] = transform.invert([
      e.clientX - rect.left,
      e.clientY - rect.top,
    ]);
    const worldHalf = currentTileSize() / transform.k / 2;

    let closest = null;
    let closestDist = Infinity;
    for (const item of renderable) {
      const x = item.x * WORLD_SIZE;
      const y = item.y * WORLD_SIZE;
      if (
        Math.abs(x - worldX) <= worldHalf &&
        Math.abs(y - worldY) <= worldHalf
      ) {
        const dist = (x - worldX) ** 2 + (y - worldY) ** 2;
        if (dist < closestDist) {
          closestDist = dist;
          closest = item;
        }
      }
    }
    if (closest) selectedItem = closest;
  }

  onMount(() => {
    if (!initGL()) return;
    loadAtlas();

    zoomBehavior = d3zoom()
      .scaleExtent([MIN_ZOOM, MAX_ZOOM])
      .on("zoom", (event) => {
        transform = event.transform;
        scheduleRender();
      });
    select(canvasEl).call(zoomBehavior).on("click", onCanvasClick);

    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
    return () => window.removeEventListener("resize", resizeCanvas);
  });

  let hasFitOnce = false;
  $effect(() => {
    if (!hasFitOnce && withCoords.length > 0 && zoomBehavior) {
      hasFitOnce = true;
      fitToCluster();
    }
  });
</script>

<div bind:this={container} class="relative h-full w-full">
  <canvas
    bind:this={canvasEl}
    class="absolute inset-0 cursor-grab active:cursor-grabbing"
  ></canvas>
</div>
