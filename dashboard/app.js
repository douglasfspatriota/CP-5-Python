/*
 * Dashboard — consome EXCLUSIVAMENTE a API FastAPI (endpoints /api/...).
 *
 * Se o dashboard for aberto pelo próprio FastAPI (http://localhost:8000/dashboard/),
 * as chamadas usam o mesmo endereço. Se for aberto de outro jeito (arquivo local,
 * Live Server etc.), usa http://localhost:8000.
 */
const API = location.pathname.startsWith("/dashboard") ? "" : "http://localhost:8000";

const estado = { liga: "", temporada: "", busca: "", pagina: 1, porPagina: 20, ordenar: "" };
const graficos = {};
let ligas = [];
let times = [];

// ------------------------------------------------------------------ utilidades
const $ = (sel) => document.querySelector(sel);
const fmt = (n, casas = 0) =>
  n === null || n === undefined ? "–" : Number(n).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const cssVar = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
const corLiga = (slug) => cssVar(`--liga-${slug}`) || cssVar("--destaque");
const escapar = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(caminho, params = {}) {
  const url = new URL(API + caminho, location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== "" && v !== null && v !== undefined) url.searchParams.set(k, v);
  });
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`${resp.status} em ${caminho}`);
  return resp.json();
}

function mostrarErro(msg) {
  const el = $("#erro");
  el.hidden = !msg;
  el.textContent = msg || "";
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ------------------------------------------------------------------ Chart.js: tema
function aplicarTemaGraficos() {
  Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.color = cssVar("--texto-3");
  Chart.defaults.borderColor = cssVar("--grade");
  Chart.defaults.plugins.tooltip.backgroundColor = cssVar("--texto");
  Chart.defaults.plugins.tooltip.titleColor = cssVar("--superficie");
  Chart.defaults.plugins.tooltip.bodyColor = cssVar("--superficie");
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 6;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.legend.labels.color = cssVar("--texto-2");
  Chart.defaults.maintainAspectRatio = false;
}

function desenhar(id, config) {
  graficos[id]?.destroy();
  graficos[id] = new Chart(document.getElementById(id), config);
}

const eixoY = (extra = {}) => ({
  grid: { color: cssVar("--grade") },
  border: { display: false },
  ticks: { color: cssVar("--texto-3") },
  ...extra,
});
const eixoX = (extra = {}) => ({
  grid: { display: false },
  border: { color: cssVar("--eixo") },
  ticks: { color: cssVar("--texto-3") },
  ...extra,
});

// ------------------------------------------------------------------ carregamento inicial
async function iniciar() {
  aplicarTemaGraficos();
  try {
    ligas = await api("/api/ligas");
  } catch (e) {
    mostrarErro("Não foi possível conectar à API. Verifique se ela está rodando (uvicorn api.main:app) e se o crawler já foi executado.");
    $("#ultima-coleta").textContent = "API indisponível";
    return;
  }
  if (!ligas.length) {
    mostrarErro("O banco está vazio. Rode o crawler primeiro: python -m crawler.main");
  }
  const sel = $("#f-liga");
  ligas.forEach((l) => sel.insertAdjacentHTML("beforeend", `<option value="${l.slug}">${escapar(l.nome)} (${escapar(l.pais)})</option>`));
  await Promise.all([carregarTemporadas(), carregarTimes()]);
  ligarEventos();
  atualizarTudo();
}

async function carregarTemporadas() {
  const temporadas = await api("/api/temporadas", { liga: estado.liga });
  const unicas = [...new Set(temporadas.map((t) => t.temporada))].sort().reverse();
  const sel = $("#f-temporada");
  sel.innerHTML = '<option value="">Todas</option>' + unicas.map((t) => `<option>${t}</option>`).join("");
  if (!unicas.includes(estado.temporada)) estado.temporada = "";
  sel.value = estado.temporada;
}

async function carregarTimes() {
  times = await api("/api/times", { liga: estado.liga });
  $("#lista-times").innerHTML = times.map((t) => `<option value="${escapar(t)}">`).join("");
}

function ligarEventos() {
  $("#f-liga").addEventListener("change", async (e) => {
    estado.liga = e.target.value;
    estado.pagina = 1;
    await Promise.all([carregarTemporadas(), carregarTimes()]);
    atualizarTudo();
  });
  $("#f-temporada").addEventListener("change", (e) => {
    estado.temporada = e.target.value;
    estado.pagina = 1;
    atualizarTabelas();
  });
  $("#f-busca").addEventListener("input", debounce((e) => {
    estado.busca = e.target.value.trim();
    estado.pagina = 1;
    atualizarTabelas();
    atualizarTrajetoria();
  }, 300));
  $("#f-limpar").addEventListener("click", async () => {
    Object.assign(estado, { liga: "", temporada: "", busca: "", pagina: 1, ordenar: "" });
    $("#f-liga").value = "";
    $("#f-busca").value = "";
    await Promise.all([carregarTemporadas(), carregarTimes()]);
    atualizarTudo();
  });
  $("#t-por-pagina").addEventListener("change", (e) => {
    estado.porPagina = Number(e.target.value);
    estado.pagina = 1;
    atualizarTabela();
  });
  $("#p-ant").addEventListener("click", () => { estado.pagina--; atualizarTabela(); });
  $("#p-prox").addEventListener("click", () => { estado.pagina++; atualizarTabela(); });
  document.querySelectorAll("#tabela th[data-campo]").forEach((th) =>
    th.addEventListener("click", () => {
      const campo = th.dataset.campo;
      const atual = estado.ordenar.replace("-", "");
      const numerico = !["time", "liga", "posicao"].includes(campo);
      if (atual !== campo) estado.ordenar = numerico ? `-${campo}` : campo;
      else estado.ordenar = estado.ordenar.startsWith("-") ? campo : `-${campo}`;
      estado.pagina = 1;
      atualizarTabela();
    })
  );
}

function atualizarTudo() {
  mostrarErro("");
  atualizarIndicadores();
  atualizarTemporadaAtual();
  atualizarGraficoGols();
  atualizarGraficoTitulos();
  atualizarGraficoDisputa();
  atualizarTabelas();
  atualizarTrajetoria();
}

function atualizarTabelas() {
  atualizarTabela();
  atualizarArtilheiros();
}

// ------------------------------------------------------------------ indicadores
async function atualizarIndicadores() {
  const r = await api("/api/estatisticas/resumo", { liga: estado.liga });
  $("#k-registros").textContent = fmt(r.total_registros);
  $("#k-registros-det").textContent = `${fmt(r.total_times)} times · ${fmt(r.total_artilheiros)} artilheiros`;
  $("#k-temporadas").textContent = fmt(r.total_temporadas);
  $("#k-temporadas-det").textContent = `${fmt(r.total_ligas)} liga(s) · ${fmt(r.total_partidas)} partidas`;
  $("#k-gols").textContent = fmt(r.media_gols_jogo, 2);
  $("#k-gols-det").textContent = `${fmt(r.total_gols)} gols no total`;
  $("#k-campeao").textContent = r.maior_campeao ? r.maior_campeao.time : "–";
  $("#k-campeao-det").textContent = r.maior_campeao ? `${r.maior_campeao.titulos} títulos · ${r.maior_campeao.liga}` : "";
  $("#k-recorde").textContent = r.recorde_pontos ? `${r.recorde_pontos.pontos} pts` : "–";
  $("#k-recorde-det").textContent = r.recorde_pontos ? `${r.recorde_pontos.time} · ${r.recorde_pontos.temporada}` : "";
  $("#k-distintos").textContent = fmt(r.campeoes_diferentes);
  $("#k-distintos-det").textContent = estado.liga ? "nesta liga" : "somando as ligas";
  $("#ultima-coleta").textContent = r.ultima_coleta
    ? `Última coleta: ${new Date(r.ultima_coleta + (r.ultima_coleta.endsWith("Z") || r.ultima_coleta.includes("+") ? "" : "Z")).toLocaleString("pt-BR")}`
    : "Nenhuma coleta registrada";
}

// ------------------------------------------------------------------ temporada atual
async function atualizarTemporadaAtual() {
  const atuais = (await api("/api/temporadas/em-andamento")).filter((t) => !estado.liga || t.liga === estado.liga);
  $("#sec-atual").hidden = !atuais.length;
  const ordem = ligas.map((l) => l.slug);
  atuais.sort((a, b) => ordem.indexOf(a.liga) - ordem.indexOf(b.liga));
  $("#atual-grade").innerHTML = atuais.map((t) => `
    <div class="atual-item" style="--cor-liga:${corLiga(t.liga)}">
      <p class="liga">${escapar(t.liga_nome)} · ${escapar(t.temporada)}</p>
      <p class="lider">${escapar(t.lider)}</p>
      <p class="det">líder, ${t.diferenca_lider_vice} pt(s) à frente</p>
      <div class="linhas">
        <span>Vice: ${escapar(t.vice)}</span>
        <span>Artilheiro: ${t.artilheiro ? `${escapar(t.artilheiro)} (${t.gols_artilheiro})` : "–"}</span>
        <span>${fmt(t.partidas)} jogos · ${fmt(t.media_gols_jogo, 2)} gols/jogo</span>
      </div>
    </div>`).join("");
}

// ------------------------------------------------------------------ gráficos
async function atualizarGraficoGols() {
  const dados = await api("/api/estatisticas/gols-por-jogo", { liga: estado.liga });
  const anos = [...new Set(dados.map((d) => d.ano_inicio))].sort();
  const porLiga = {};
  dados.forEach((d) => { (porLiga[d.liga] ??= { nome: d.liga_nome, pontos: {} }).pontos[d.ano_inicio] = d; });
  const ordem = ligas.map((l) => l.slug).filter((s) => porLiga[s]);
  desenhar("g-gols", {
    type: "line",
    data: {
      labels: anos.map(String),
      datasets: ordem.map((slug) => ({
        label: porLiga[slug].nome,
        data: anos.map((a) => porLiga[slug].pontos[a]?.media_gols_jogo ?? null),
        temporadas: anos.map((a) => {
          const p = porLiga[slug].pontos[a];
          return p ? p.temporada + (p.campeao ? "" : ", em andamento") : "";
        }),
        borderColor: corLiga(slug),
        backgroundColor: corLiga(slug),
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 6,
        pointBorderColor: cssVar("--superficie"),
        pointBorderWidth: 2,
        tension: 0.25,
        spanGaps: true,
      })),
    },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            title: (itens) => `Temporada iniciada em ${itens[0].label}`,
            label: (c) => ` ${c.dataset.label} (${c.dataset.temporadas[c.dataIndex]}): ${fmt(c.parsed.y, 2)} gols/jogo`,
          },
        },
      },
      scales: {
        x: eixoX({ title: { display: true, text: "Ano de início da temporada", color: cssVar("--texto-3") } }),
        y: eixoY({ title: { display: true, text: "Gols por jogo", color: cssVar("--texto-3") }, ticks: { callback: (v) => fmt(v, 1) } }),
      },
    },
  });
}

async function atualizarGraficoTitulos() {
  const dados = await api("/api/estatisticas/titulos", { liga: estado.liga, limite: 10 });
  const slugPorNome = Object.fromEntries(ligas.map((l) => [l.nome, l.slug]));
  const presentes = [...new Set(dados.map((d) => d.liga))];
  $("#leg-titulos").innerHTML = presentes.length > 1
    ? presentes.map((n) => `<span><span class="ponto-liga" style="background:${corLiga(slugPorNome[n])}"></span>${escapar(n)}</span>`).join("")
    : "";
  desenhar("g-titulos", {
    type: "bar",
    data: {
      labels: dados.map((d) => d.time),
      datasets: [{
        label: "Títulos",
        data: dados.map((d) => d.titulos),
        backgroundColor: dados.map((d) => corLiga(slugPorNome[d.liga])),
        borderRadius: 4,
        borderSkipped: "start",
        barPercentage: 0.75,
        categoryPercentage: 0.9,
      }],
    },
    options: {
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (i) => `${dados[i[0].dataIndex].time} · ${dados[i[0].dataIndex].liga}`,
            label: (c) => ` ${c.parsed.x} título(s): ${dados[c.dataIndex].temporadas.join(", ")}`,
          },
        },
      },
      scales: {
        x: eixoY({ beginAtZero: true, ticks: { precision: 0, color: cssVar("--texto-3") } }),
        y: eixoX({ ticks: { color: cssVar("--texto-2") } }),
      },
    },
  });
}

async function atualizarGraficoDisputa() {
  if (!estado.liga) {
    // Visão geral: uma barra por liga com a diferença média entre 1º e 2º
    const dados = await api("/api/estatisticas/ligas");
    $("#g-disputa-titulo").textContent = "Equilíbrio das ligas";
    $("#g-disputa-sub").textContent = "Diferença média de pontos entre 1º e 2º colocados (menor = mais disputada)";
    desenhar("g-disputa", {
      type: "bar",
      data: {
        labels: dados.map((d) => d.liga_nome),
        datasets: [{
          label: "Diferença média (pts)",
          data: dados.map((d) => d.media_diferenca_lider_vice),
          backgroundColor: dados.map((d) => corLiga(d.liga)),
          borderRadius: 4,
          borderSkipped: "start",
          barPercentage: 0.7,
        }],
      },
      options: {
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c) => {
                const d = dados[c.dataIndex];
                return [` ${fmt(d.media_diferenca_lider_vice, 1)} pts de diferença em média`,
                        ` ${d.campeoes_diferentes} campeões diferentes em ${d.temporadas} temporadas`];
              },
            },
          },
        },
        scales: { x: eixoX(), y: eixoY({ beginAtZero: true, title: { display: true, text: "Pontos", color: cssVar("--texto-3") } }) },
      },
    });
    return;
  }
  // Liga selecionada: uma barra por temporada
  const dados = await api("/api/estatisticas/disputa", { liga: estado.liga });
  const nome = ligas.find((l) => l.slug === estado.liga)?.nome ?? "";
  $("#g-disputa-titulo").textContent = `Disputa pelo título · ${nome}`;
  $("#g-disputa-sub").textContent = "Pontos de vantagem do 1º colocado sobre o 2º em cada temporada";
  desenhar("g-disputa", {
    type: "bar",
    data: {
      labels: dados.map((d) => d.temporada),
      datasets: [{
        label: "Vantagem (pts)",
        data: dados.map((d) => d.diferenca_lider_vice),
        backgroundColor: corLiga(estado.liga),
        borderRadius: 4,
        borderSkipped: "start",
        barPercentage: 0.7,
      }],
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const d = dados[c.dataIndex];
              const andamento = d.campeao ? "" : " (em andamento)";
              return [` ${d.lider} ${d.diferenca_lider_vice} pts à frente${andamento}`, ` Vice: ${d.vice}`];
            },
          },
        },
      },
      scales: { x: eixoX(), y: eixoY({ beginAtZero: true, ticks: { precision: 0, color: cssVar("--texto-3") } }) },
    },
  });
}

async function atualizarTrajetoria() {
  const alvo = times.find((t) => t.toLowerCase() === estado.busca.toLowerCase());
  const vazio = $("#g-time-vazio");
  if (!alvo) {
    graficos["g-time"]?.destroy();
    delete graficos["g-time"];
    vazio.hidden = false;
    vazio.parentElement.classList.add("recolhido");
    vazio.textContent = estado.busca ? "Escolha um nome da lista de sugestões para ver a trajetória." : "Nenhum time selecionado.";
    $("#g-time-titulo").textContent = "Trajetória de um time";
    $("#g-time-sub").textContent = "Busque um time no filtro acima para ver a posição dele em cada temporada";
    return;
  }
  const hist = await api(`/api/times/${encodeURIComponent(alvo)}/historico`);
  vazio.hidden = true;
  vazio.parentElement.classList.remove("recolhido");
  const titulos = hist.filter((h) => h.campeao).length;
  $("#g-time-titulo").textContent = `Trajetória · ${alvo}`;
  $("#g-time-sub").textContent = `${hist[0].liga_nome} · ${hist.length} temporada(s) coletada(s) · ${titulos} título(s)`;
  const maxTimes = Math.max(...hist.map((h) => h.total_times));
  const cor = corLiga(hist[0].liga);
  desenhar("g-time", {
    type: "line",
    data: {
      labels: hist.map((h) => h.temporada),
      datasets: [{
        label: "Posição final",
        data: hist.map((h) => h.posicao),
        borderColor: cor,
        backgroundColor: cor,
        borderWidth: 2,
        pointRadius: hist.map((h) => (h.campeao ? 7 : 4)),
        pointStyle: hist.map((h) => (h.campeao ? "star" : "circle")),
        pointHoverRadius: 8,
        pointBorderColor: hist.map((h) => (h.campeao ? cor : cssVar("--superficie"))),
        pointBorderWidth: 2,
        tension: 0.2,
      }],
    },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const h = hist[c.dataIndex];
              const selo = h.campeao ? " · Campeão" : h.rebaixado ? " · Rebaixado" : "";
              return [` ${h.posicao}º lugar${selo}`, ` ${h.pontos} pts · ${h.vitorias}V ${h.empates}E ${h.derrotas}D · ${fmt(h.aproveitamento, 1)}%`];
            },
          },
        },
      },
      scales: {
        x: eixoX(),
        y: eixoY({ reverse: true, min: 1, max: maxTimes, ticks: { precision: 0, maxTicksLimit: 10, color: cssVar("--texto-3"), callback: (v) => (Number.isInteger(v) ? `${v}º` : "") },
                   title: { display: true, text: "Posição (1º no topo)", color: cssVar("--texto-3") } }),
      },
    },
  });
}

// ------------------------------------------------------------------ tabelas
async function atualizarTabela() {
  const r = await api("/api/classificacoes", {
    liga: estado.liga, temporada: estado.temporada, busca: estado.busca,
    ordenar: estado.ordenar, pagina: estado.pagina, por_pagina: estado.porPagina,
  });
  const corpo = $("#tabela tbody");
  corpo.innerHTML = r.itens.length
    ? r.itens.map((d) => `
      <tr>
        <td class="num">${d.posicao}º</td>
        <td class="time">${escapar(d.time)}${d.campeao ? '<span class="selo campeao">🏆 Campeão</span>' : ""}${d.rebaixado ? '<span class="selo rebaixado">↓ Rebaixado</span>' : ""}</td>
        <td><span class="ponto-liga" style="background:${corLiga(d.liga)}"></span>${escapar(d.liga_nome)}</td>
        <td>${escapar(d.temporada)}${!d.campeao && !d.temporada_encerrada && d.posicao === 1 ? '<span class="selo andamento">Líder</span>' : ""}</td>
        <td class="num"><strong>${d.pontos}</strong></td>
        <td class="num">${d.jogos}</td>
        <td class="num">${d.vitorias}</td>
        <td class="num">${d.empates}</td>
        <td class="num">${d.derrotas}</td>
        <td class="num">${d.gols_pro ?? "–"}</td>
        <td class="num">${d.gols_contra ?? "–"}</td>
        <td class="num">${d.saldo > 0 ? "+" : ""}${d.saldo ?? "–"}</td>
        <td class="num">${fmt(d.aproveitamento, 1)}%</td>
      </tr>`).join("")
    : '<tr><td colspan="13" class="sem-dados">Nenhum registro encontrado para esses filtros.</td></tr>';

  $("#t-info").textContent = `${fmt(r.total)} registro(s) encontrado(s)`;
  $("#p-info").textContent = `Página ${r.pagina} de ${r.total_paginas}`;
  $("#p-ant").disabled = r.pagina <= 1;
  $("#p-prox").disabled = r.pagina >= r.total_paginas;

  const campo = estado.ordenar.replace("-", "");
  document.querySelectorAll("#tabela th[data-campo]").forEach((th) => {
    th.classList.toggle("ordenado", th.dataset.campo === campo);
    th.classList.toggle("desc", th.dataset.campo === campo && estado.ordenar.startsWith("-"));
  });
}

async function atualizarArtilheiros() {
  const r = await api("/api/artilheiros", {
    liga: estado.liga, temporada: estado.temporada, busca: estado.busca, por_pagina: 10,
  });
  $("#a-info").textContent = `Top 10 de ${fmt(r.total)} registro(s) conforme os filtros`;
  $("#tabela-art tbody").innerHTML = r.itens.length
    ? r.itens.map((a, i) => `
      <tr>
        <td class="num">${i + 1}</td>
        <td class="time">${escapar(a.jogador)}</td>
        <td>${escapar(a.time ?? "–")}</td>
        <td><span class="ponto-liga" style="background:${corLiga(a.liga)}"></span>${escapar(a.liga_nome)}</td>
        <td>${escapar(a.temporada)}</td>
        <td class="num"><strong>${a.gols}</strong></td>
      </tr>`).join("")
    : '<tr><td colspan="6" class="sem-dados">Nenhum artilheiro encontrado.</td></tr>';
}

// Erros inesperados aparecem num aviso em vez de travar a página
window.addEventListener("unhandledrejection", (e) => mostrarErro(`Erro ao consultar a API: ${e.reason?.message ?? e.reason}`));

iniciar();
