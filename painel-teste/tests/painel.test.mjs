// node --test painel-teste/tests/
import assert from "node:assert/strict";
import test from "node:test";

import { conectar, formatar, novoEstado, reduzir, renderizar } from "../painel.mjs";

const msgTabela = (rpm, ect = 90) => ({
  tipo: "tabela", t: 1.0, tabela: "11", bruto: "0219711109c4",
  valores: {
    rpm: { valor: rpm, unidade: "rpm", status: "HIPOTESE", min: 0, max: 9000 },
    ect: { valor: ect, unidade: "°C", status: "HIPOTESE", min: -40, max: 140 },
    tensao: { valor: 14.08, unidade: "V", status: "HIPOTESE", min: 0, max: 18 },
  },
});

test("formatar usa casas por sensor", () => {
  assert.equal(formatar("rpm", 761.6), "762");
  assert.equal(formatar("o2", 0.456), "0.46");
  assert.equal(formatar("tensao", 14.08), "14.1");
});

test("render mostra valores, unidade, selo de hipótese e quadro cru", () => {
  const e = reduzir(reduzir(novoEstado(), { tipo: "estado", estado: "ativo" }), msgTabela(761.6));
  const html = renderizar(e);
  assert.match(html, /ECU respondendo · 1 quadros/);
  assert.match(html, /data-sensor="rpm".*<b>762<\/b> <small>rpm<\/small>/s);
  assert.match(html, /Temp\. motor <span class="selo">hipótese<\/span>/);
  assert.match(html, /<b>14\.1<\/b> <small>V<\/small>/);
  assert.match(html, /<b>11<\/b> <code>0219711109c4<\/code>/);
  assert.ok(html.indexOf('data-sensor="rpm"') < html.indexOf('data-sensor="ect"'), "ordem fixa");
});

test("valor fora da faixa marca o cartão e a barra fica presa em 0..100%", () => {
  const html = renderizar(reduzir(novoEstado(), msgTabela(9500, -50)));
  assert.match(html, /class="cartao fora" data-sensor="rpm".*width:100%/s);
  assert.match(html, /class="cartao fora" data-sensor="ect"[^]*?width:0%/);
});

test("render escapa texto vindo da ponte", () => {
  const html = renderizar(reduzir(novoEstado(), { tipo: "estado", estado: "erro", detalhe: "<img src=x>" }));
  assert.ok(!html.includes("<img"));
  assert.match(html, /erro na porta — &#60;img src=x&#62;/);
});

test("conectar desenha a cada mensagem e reconecta quando o socket fecha", () => {
  const sockets = [];
  class WSFalso { constructor(url) { this.url = url; sockets.push(this); } }
  const agendados = [];
  const alvo = { innerHTML: "" };
  const estado = conectar("ws://x/ws", alvo, WSFalso, (fn, ms) => agendados.push([fn, ms]));
  assert.match(alvo.innerHTML, /desconectado da ponte/);
  sockets[0].onmessage({ data: JSON.stringify({ tipo: "estado", estado: "ativo" }) });
  sockets[0].onmessage({ data: JSON.stringify(msgTabela(800)) });
  assert.match(alvo.innerHTML, /<b>800<\/b>/);
  assert.equal(estado().recebidas, 1);
  sockets[0].onclose();
  assert.match(alvo.innerHTML, /desconectado da ponte/);
  assert.match(alvo.innerHTML, /<b>800<\/b>/, "último valor continua visível");
  assert.equal(agendados[0][1], 1000);
  agendados[0][0]();
  assert.equal(sockets.length, 2);
});
