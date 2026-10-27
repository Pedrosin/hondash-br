// Painel de teste: estado puro + render em string (testável no node sem DOM).
export const ORDEM = ["rpm", "vss", "ect", "iat", "map", "tps", "o2", "avanco", "tensao"];
export const ROTULOS = {
  rpm: "Rotação", vss: "Velocidade", ect: "Temp. motor", iat: "Temp. ar", map: "Pressão coletor",
  tps: "Borboleta", o2: "Sonda lambda", avanco: "Avanço", tensao: "Bateria",
};
const CASAS = { o2: 2, avanco: 1, tensao: 1 };
const ESTADOS = {
  desconectado: "desconectado da ponte", iniciando: "iniciando", ativo: "ECU respondendo",
  sem_resposta: "ECU não responde", reconectando: "reconectando", erro: "erro na porta",
};

export function novoEstado() {
  return { conexao: "desconectado", detalhe: "", valores: {}, bruto: {}, recebidas: 0 };
}

export function reduzir(estado, msg) {
  if (msg.tipo === "estado") return { ...estado, conexao: msg.estado, detalhe: msg.detalhe || "" };
  if (msg.tipo === "tabela") {
    return {
      ...estado,
      valores: { ...estado.valores, ...msg.valores },
      bruto: { ...estado.bruto, [msg.tabela]: msg.bruto },
      recebidas: estado.recebidas + 1,
    };
  }
  return estado;
}

export function formatar(nome, valor) {
  return Number(valor).toFixed(CASAS[nome] ?? 0);
}

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function cartao(nome, v) {
  const fora = v.valor < v.min || v.valor > v.max;
  const pct = Math.max(0, Math.min(100, ((v.valor - v.min) / (v.max - v.min)) * 100));
  const selo = v.status === "HIPOTESE" ? '<span class="selo">hipótese</span>' : "";
  return `<section class="cartao${fora ? " fora" : ""}" data-sensor="${esc(nome)}">` +
    `<h2>${esc(ROTULOS[nome] ?? nome)} ${selo}</h2>` +
    `<p class="valor"><b>${esc(formatar(nome, v.valor))}</b> <small>${esc(v.unidade)}</small></p>` +
    `<div class="trilho"><div class="barra" style="width:${pct.toFixed(0)}%"></div></div></section>`;
}

export function renderizar(estado) {
  const nomes = [...ORDEM.filter((n) => n in estado.valores),
    ...Object.keys(estado.valores).filter((n) => !ORDEM.includes(n))];
  const cartoes = nomes.map((n) => cartao(n, estado.valores[n])).join("");
  const bruto = Object.entries(estado.bruto)
    .map(([t, hex]) => `<li><b>${esc(t)}</b> <code>${esc(hex)}</code></li>`).join("");
  return `<p id="conexao" class="conexao ${esc(estado.conexao)}">${esc(ESTADOS[estado.conexao] ?? estado.conexao)}` +
    `${estado.detalhe ? ` — ${esc(estado.detalhe)}` : ""} · ${estado.recebidas} quadros</p>` +
    `<div class="grade">${cartoes || "<p>aguardando dados…</p>"}</div>` +
    `<ul class="bruto">${bruto}</ul>`;
}

// Liga o painel a um WebSocket. WS e agendar são injetáveis para teste.
export function conectar(url, alvo, WS = globalThis.WebSocket, agendar = globalThis.setTimeout) {
  let estado = novoEstado();
  const desenhar = () => { alvo.innerHTML = renderizar(estado); };
  const abrir = () => {
    const ws = new WS(url);
    ws.onmessage = (ev) => { estado = reduzir(estado, JSON.parse(ev.data)); desenhar(); };
    ws.onclose = () => {
      estado = reduzir(estado, { tipo: "estado", estado: "desconectado" });
      desenhar();
      agendar(abrir, 1000);
    };
  };
  desenhar();
  abrir();
  return () => estado;
}
