const SVG_NS = "http://www.w3.org/2000/svg";
const NODE_RADIUS = 22;
const PADDING = 40;
const MIN_EDGE_WIDTH = 1;
const MAX_EDGE_WIDTH = 6;
const REPULSION_STRENGTH = 1200;
const SPRING_STRENGTH = 0.02;
const SPRING_REST_LENGTH = 90;
const DAMPING = 0.85;

class ChainGraph {
  constructor(svgEl, tooltipEl) {
    this.svg = svgEl;
    this.tooltip = tooltipEl;
    this.width = Number(svgEl.getAttribute("width"));
    this.height = Number(svgEl.getAttribute("height"));
    this.threshold = 0.15;
    this.nodes = [];
    this.edges = [];
    this.nodeEls = new Map();
    this.edgeEls = new Map();
    this._nextId = 1;
    this.dragNode = null;
    this._tick = this._tick.bind(this);
    requestAnimationFrame(this._tick);
  }

  reset(startWord, targetWord) {
    this.svg.innerHTML = "";
    this.nodeEls.clear();
    this.edgeEls.clear();
    this._nextId = 1;
    this.nodes = [
      this._makeNode(startWord, PADDING, this.height / 2, true),
      this._makeNode(targetWord, this.width - PADDING, this.height / 2, true),
    ];
    this.edges = [];
    for (const node of this.nodes) {
      this._createNodeEl(node);
    }
  }

  addStep(step) {
    const prevNode = this.nodes[this.nodes.length - 2];
    const targetNode = this.nodes[this.nodes.length - 1];

    if (step.word === targetNode.word) {
      // The player's word IS the pinned target: connect into the existing
      // target node instead of creating a duplicate.
      targetNode.neighborSimilarity = step.neighbor_similarity;
      targetNode.targetSimilarity = step.target_similarity;
      targetNode.isDigression = step.is_digression;
      this._updateNodeAppearance(targetNode);

      const edge = { aId: prevNode.id, bId: targetNode.id, similarity: step.neighbor_similarity };
      this.edges.push(edge);
      this._createEdgeEl(edge);
      return;
    }

    const rawX = prevNode.x + (Math.random() - 0.5) * 60;
    const rawY = prevNode.y + (Math.random() - 0.5) * 60;
    const x = Math.max(NODE_RADIUS, Math.min(this.width - NODE_RADIUS, rawX));
    const y = Math.max(NODE_RADIUS, Math.min(this.height - NODE_RADIUS, rawY));

    const node = this._makeNode(step.word, x, y, false);
    node.neighborSimilarity = step.neighbor_similarity;
    node.targetSimilarity = step.target_similarity;
    node.isDigression = step.is_digression;

    this.nodes.splice(this.nodes.length - 1, 0, node);
    const edge = { aId: prevNode.id, bId: node.id, similarity: step.neighbor_similarity };
    this.edges.push(edge);

    this._createNodeEl(node);
    this._createEdgeEl(edge);
  }

  setThreshold(value) {
    this.threshold = value;
    this._renderEdges();
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
      neighborSimilarity: null,
      targetSimilarity: null,
    };
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
    if (node.pinned) circle.classList.add("node-pinned");
    g.appendChild(circle);

    const text = document.createElementNS(SVG_NS, "text");
    text.textContent = node.word;
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("dy", "0.35em");
    g.appendChild(text);

    this.svg.appendChild(g);
    this.nodeEls.set(node.id, { g, circle, text });
    this._updateNodeAppearance(node);
  }

  _updateNodeAppearance(node) {
    const els = this.nodeEls.get(node.id);
    if (!els) return;
    els.circle.classList.toggle("node-digression", node.isDigression);
  }

  _createEdgeEl(edge) {
    const line = document.createElementNS(SVG_NS, "line");
    line.classList.add("edge");
    this.svg.insertBefore(line, this.svg.firstChild);
    this.edgeEls.set(edge, line);
    this._renderEdge(edge);
  }

  _renderEdge(edge) {
    const line = this.edgeEls.get(edge);
    const a = this._nodeById(edge.aId);
    const b = this._nodeById(edge.bId);
    if (!line || !a || !b) return;

    const visible = edge.similarity >= this.threshold;
    line.style.display = visible ? "" : "none";
    if (!visible) return;

    line.setAttribute("x1", a.x);
    line.setAttribute("y1", a.y);
    line.setAttribute("x2", b.x);
    line.setAttribute("y2", b.y);
    const width = MIN_EDGE_WIDTH + edge.similarity * (MAX_EDGE_WIDTH - MIN_EDGE_WIDTH);
    line.setAttribute("stroke-width", width.toFixed(2));
    line.style.opacity = Math.max(0.25, edge.similarity).toFixed(2);
  }

  _renderEdges() {
    for (const edge of this.edges) {
      this._renderEdge(edge);
    }
  }

  _tick() {
    this._applyForces();
    this._render();
    requestAnimationFrame(this._tick);
  }

  _applyForces() {
    for (const node of this.nodes) {
      if (node.pinned || node === this.dragNode) continue;

      let fx = 0;
      let fy = 0;

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
}
