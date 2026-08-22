const SVG_NS = "http://www.w3.org/2000/svg";
const NODE_RADIUS = 28;
const PADDING = 50;
const MIN_EDGE_WIDTH = 1;
const MAX_EDGE_WIDTH = 6;
const MIN_EDGE_OPACITY = 0.35;
const MAX_EDGE_OPACITY = 1.0;
const REPULSION_STRENGTH = 1200;
const SPRING_STRENGTH = 0.02;
const SPRING_REST_LENGTH = 110;
const CENTER_STRENGTH = 0.0015;
const DAMPING = 0.85;

class ChainGraph {
  constructor(svgEl, tooltipEl) {
    this.svg = svgEl;
    this.tooltip = tooltipEl;
    this.width = Number(svgEl.getAttribute("width"));
    this.height = Number(svgEl.getAttribute("height"));
    this.threshold = 0.7;
    this.nodes = [];
    this.edges = [];
    this.nodeEls = new Map();
    this.edgeEls = new Map();
    this.edgeLabelEls = new Map();
    this._winningEdges = new Set();
    this._suggestedEdges = new Set();
    this._nodesByWord = new Map();
    this._nextId = 1;
    this.dragNode = null;

    this._tick = this._tick.bind(this);
    requestAnimationFrame(this._tick);

    this.svg.addEventListener("mousedown", (evt) => this._onMouseDown(evt));
    window.addEventListener("mousemove", (evt) => this._onMouseMove(evt));
    window.addEventListener("mouseup", () => this._onMouseUp());
  }

  reset(startWord, targetWord, startTargetSimilarity) {
    this.svg.innerHTML = "";
    this.nodeEls.clear();
    this.edgeEls.clear();
    this.edgeLabelEls.clear();
    this._winningEdges = new Set();
    this._suggestedEdges = new Set();
    this._nodesByWord.clear();
    this._nextId = 1;
    this.dragNode = null;
    this._hideTooltip();

    const startNode = this._makeNode(startWord, PADDING, this.height / 2, true);
    const targetNode = this._makeNode(targetWord, this.width - PADDING, this.height / 2, true);
    this.nodes = [startNode, targetNode];
    this.edges = [];

    for (const node of this.nodes) {
      this._createNodeEl(node);
    }

    if (typeof startTargetSimilarity === "number") {
      const edge = { aId: startNode.id, bId: targetNode.id, similarity: startTargetSimilarity };
      this.edges.push(edge);
      this._createEdgeEl(edge);
    }
  }

  addStep(step) {
    const anchor = this.nodes[this.nodes.length - 1];
    const rawX = anchor.x + (Math.random() - 0.5) * 60;
    const rawY = anchor.y + (Math.random() - 0.5) * 60;
    const x = Math.max(NODE_RADIUS, Math.min(this.width - NODE_RADIUS, rawX));
    const y = Math.max(NODE_RADIUS, Math.min(this.height - NODE_RADIUS, rawY));

    const node = this._makeNode(step.word, x, y, false);
    node.neighborSimilarity = step.neighbor_similarity;
    node.targetSimilarity = step.target_similarity;
    node.isDigression = step.is_digression;

    this.nodes.push(node);
    this._createNodeEl(node);

    const used = new Map();
    for (const entry of step.similarities || []) {
      const ids = this._nodesByWord.get(entry.word) || [];
      const k = used.get(entry.word) || 0;
      used.set(entry.word, k + 1);
      const otherId = ids[k];
      if (otherId === undefined || otherId === node.id) continue;
      const edge = { aId: node.id, bId: otherId, similarity: entry.similarity };
      this.edges.push(edge);
      this._createEdgeEl(edge);
    }
  }

  setThreshold(value) {
    this.threshold = value;
  }

  highlightWinningConnection(connection) {
    this._winningEdges = new Set();
    for (const link of connection || []) {
      const edge = this._findEdgeForWordPair(link.a, link.b);
      if (edge) this._winningEdges.add(edge);
    }
    this._renderEdges();
  }

  showSuggestedRoute(route) {
    if (!route || route.length < 2) return;

    const routeNodes = route.map((word) => this._getOrCreateNode(word));
    for (let i = 0; i < routeNodes.length - 1; i++) {
      const a = routeNodes[i];
      const b = routeNodes[i + 1];
      let edge = this._findEdgeForWordPair(a.word, b.word);
      if (!edge) {
        edge = { aId: a.id, bId: b.id, similarity: 1 };
        this.edges.push(edge);
        this._createEdgeEl(edge);
      }
      this._suggestedEdges.add(edge);
    }
    this._renderEdges();
  }

  _getOrCreateNode(word) {
    const existingIds = this._nodesByWord.get(word);
    if (existingIds && existingIds.length) {
      return this._nodeById(existingIds[existingIds.length - 1]);
    }
    const anchor = this.nodes[this.nodes.length - 1];
    const rawX = anchor ? anchor.x + (Math.random() - 0.5) * 60 : this.width / 2;
    const rawY = anchor ? anchor.y + (Math.random() - 0.5) * 60 : this.height / 2;
    const x = Math.max(NODE_RADIUS, Math.min(this.width - NODE_RADIUS, rawX));
    const y = Math.max(NODE_RADIUS, Math.min(this.height - NODE_RADIUS, rawY));

    const node = this._makeNode(word, x, y, false);
    node.isSuggested = true;
    this.nodes.push(node);
    this._createNodeEl(node);
    return node;
  }

  _findEdgeForWordPair(wordA, wordB) {
    for (const edge of this.edges) {
      const a = this._nodeById(edge.aId);
      const b = this._nodeById(edge.bId);
      if (!a || !b) continue;
      if ((a.word === wordA && b.word === wordB) || (a.word === wordB && b.word === wordA)) {
        return edge;
      }
    }
    return null;
  }

  _makeNode(word, x, y, pinned) {
    return {
      id: this._nextId++,
      word,
      x,
      y,
      vx: 0,
      vy: 0,
      pinned,
      isDigression: false,
      isSuggested: false,
      neighborSimilarity: null,
      targetSimilarity: null,
    };
  }

  _fontSizeForWord(word) {
    const maxWidth = NODE_RADIUS * 2 - 8;
    const estimatedCharWidth = 0.6;
    const fitted = maxWidth / (word.length * estimatedCharWidth);
    return Math.max(8, Math.min(14, fitted));
  }

  _nodeById(id) {
    return this.nodes.find((n) => n.id === id);
  }

  _createNodeEl(node) {
    const g = document.createElementNS(SVG_NS, "g");
    g.classList.add("node");
    g.dataset.nodeId = String(node.id);
    g.setAttribute("transform", `translate(${node.x}, ${node.y})`);

    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("r", NODE_RADIUS);
    g.appendChild(circle);

    const text = document.createElementNS(SVG_NS, "text");
    text.textContent = node.word;
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("dy", "0.35em");
    text.style.fontSize = `${this._fontSizeForWord(node.word)}px`;
    g.appendChild(text);

    g.addEventListener("mouseenter", (evt) => this._showTooltip(node, evt));
    g.addEventListener("mousemove", (evt) => this._positionTooltip(evt));
    g.addEventListener("mouseleave", () => this._hideTooltip());

    this.svg.appendChild(g);
    this.nodeEls.set(node.id, { g, circle, text });

    if (!this._nodesByWord.has(node.word)) {
      this._nodesByWord.set(node.word, []);
    }
    this._nodesByWord.get(node.word).push(node.id);

    this._updateNodeAppearance(node);
  }

  _updateNodeAppearance(node) {
    const els = this.nodeEls.get(node.id);
    if (!els) return;
    els.circle.classList.toggle("node-pinned", node.pinned);
    els.circle.classList.toggle("node-digression", node.isDigression);
    els.circle.classList.toggle("node-suggested", node.isSuggested);
  }

  _createEdgeEl(edge) {
    const line = document.createElementNS(SVG_NS, "line");
    line.classList.add("edge");
    this.svg.insertBefore(line, this.svg.firstChild);
    this.edgeEls.set(edge, line);
  }

  _renderEdge(edge, maxSimilarity) {
    const line = this.edgeEls.get(edge);
    const a = this._nodeById(edge.aId);
    const b = this._nodeById(edge.bId);
    if (!line || !a || !b) return;

    const isWinning = this._winningEdges.has(edge);
    const isSuggested = this._suggestedEdges.has(edge);
    const visible = edge.similarity >= this.threshold || isWinning || isSuggested;
    line.style.display = visible ? "" : "none";
    line.classList.toggle("edge-winning", isWinning);
    line.classList.toggle("edge-suggested", isSuggested);
    if (!visible) {
      this._removeEdgeLabel(edge);
      return;
    }

    line.setAttribute("x1", a.x);
    line.setAttribute("y1", a.y);
    line.setAttribute("x2", b.x);
    line.setAttribute("y2", b.y);

    if (isWinning) {
      line.setAttribute("stroke-width", MAX_EDGE_WIDTH.toFixed(2));
      line.style.opacity = "1";
      this._renderEdgeLabel(edge, a, b);
    } else if (isSuggested) {
      line.setAttribute("stroke-width", MAX_EDGE_WIDTH.toFixed(2));
      line.style.opacity = "1";
      this._removeEdgeLabel(edge);
    } else {
      const range = Math.max(maxSimilarity - this.threshold, 0.0001);
      const normalized = Math.min(1, Math.max(0, (edge.similarity - this.threshold) / range));
      const width = MIN_EDGE_WIDTH + normalized * (MAX_EDGE_WIDTH - MIN_EDGE_WIDTH);
      const opacity = MIN_EDGE_OPACITY + normalized * (MAX_EDGE_OPACITY - MIN_EDGE_OPACITY);
      line.setAttribute("stroke-width", width.toFixed(2));
      line.style.opacity = opacity.toFixed(2);
      this._removeEdgeLabel(edge);
    }
  }

  _renderEdgeLabel(edge, a, b) {
    let text = this.edgeLabelEls.get(edge);
    if (!text) {
      text = document.createElementNS(SVG_NS, "text");
      text.classList.add("edge-label");
      text.setAttribute("text-anchor", "middle");
      this.svg.appendChild(text);
      this.edgeLabelEls.set(edge, text);
    }
    text.textContent = edge.similarity.toFixed(2);
    text.setAttribute("x", (a.x + b.x) / 2);
    text.setAttribute("y", (a.y + b.y) / 2 - 6);
  }

  _removeEdgeLabel(edge) {
    const text = this.edgeLabelEls.get(edge);
    if (!text) return;
    text.remove();
    this.edgeLabelEls.delete(edge);
  }

  _renderEdges() {
    let maxSimilarity = this.threshold;
    for (const edge of this.edges) {
      if (edge.similarity >= this.threshold && edge.similarity > maxSimilarity) {
        maxSimilarity = edge.similarity;
      }
    }
    for (const edge of this.edges) {
      this._renderEdge(edge, maxSimilarity);
    }
  }

  _tick() {
    this._applyForces();
    this._render();
    requestAnimationFrame(this._tick);
  }

  _applyForces() {
    const cx = this.width / 2;
    const cy = this.height / 2;

    for (const node of this.nodes) {
      if (node.pinned || node === this.dragNode) continue;

      let fx = (cx - node.x) * CENTER_STRENGTH;
      let fy = (cy - node.y) * CENTER_STRENGTH;

      for (const other of this.nodes) {
        if (other === node) continue;
        let dx = node.x - other.x;
        let dy = node.y - other.y;
        let distSq = dx * dx + dy * dy;
        if (distSq < 1) distSq = 1;
        const dist = Math.sqrt(distSq);
        const force = REPULSION_STRENGTH / distSq;
        fx += (dx / dist) * force;
        fy += (dy / dist) * force;
      }

      for (const edge of this.edges) {
        if (edge.similarity < this.threshold) continue;
        let otherId = null;
        if (edge.aId === node.id) otherId = edge.bId;
        else if (edge.bId === node.id) otherId = edge.aId;
        else continue;
        const other = this._nodeById(otherId);
        if (!other) continue;

        const dx = other.x - node.x;
        const dy = other.y - node.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const displacement = dist - SPRING_REST_LENGTH;
        const force = SPRING_STRENGTH * displacement;
        fx += (dx / dist) * force;
        fy += (dy / dist) * force;
      }

      node.vx = (node.vx + fx) * DAMPING;
      node.vy = (node.vy + fy) * DAMPING;
      node.x += node.vx;
      node.y += node.vy;
      node.x = Math.max(NODE_RADIUS, Math.min(this.width - NODE_RADIUS, node.x));
      node.y = Math.max(NODE_RADIUS, Math.min(this.height - NODE_RADIUS, node.y));
    }
  }

  _render() {
    for (const node of this.nodes) {
      const els = this.nodeEls.get(node.id);
      if (els) els.g.setAttribute("transform", `translate(${node.x}, ${node.y})`);
    }
    this._renderEdges();
  }

  _svgPoint(evt) {
    const pt = this.svg.createSVGPoint();
    pt.x = evt.clientX;
    pt.y = evt.clientY;
    const screenCTM = this.svg.getScreenCTM();
    return pt.matrixTransform(screenCTM.inverse());
  }

  _onMouseDown(evt) {
    const g = evt.target.closest(".node");
    if (!g) return;
    const nodeId = Number(g.dataset.nodeId);
    const node = this._nodeById(nodeId);
    if (!node || node.pinned) return;
    this.dragNode = node;
  }

  _onMouseMove(evt) {
    if (!this.dragNode) return;
    const pt = this._svgPoint(evt);
    this.dragNode.x = Math.max(NODE_RADIUS, Math.min(this.width - NODE_RADIUS, pt.x));
    this.dragNode.y = Math.max(NODE_RADIUS, Math.min(this.height - NODE_RADIUS, pt.y));
    this.dragNode.vx = 0;
    this.dragNode.vy = 0;
  }

  _onMouseUp() {
    this.dragNode = null;
  }

  _showTooltip(node, evt) {
    const text = node.neighborSimilarity === null
      ? node.word
      : `${node.word} — neighbor: ${node.neighborSimilarity.toFixed(2)}, target: ${node.targetSimilarity.toFixed(2)}`;
    this.tooltip.textContent = text;
    this.tooltip.hidden = false;
    this._positionTooltip(evt);
  }

  _positionTooltip(evt) {
    this.tooltip.style.left = `${evt.clientX + 12}px`;
    this.tooltip.style.top = `${evt.clientY + 12}px`;
  }

  _hideTooltip() {
    this.tooltip.hidden = true;
  }
}
