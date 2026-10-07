# Futebol em Números: Web Crawler, API e Dashboard

**Integrantes do grupo**

| Nome | RM |
|---|---|
| Douglas Patriota | RM569713 |
| Vitor Cintra | RM569416 |
| Octavio Kal | RM571838 |
| Pedro Brito | RM573187 |
| Guilherme Zeferino | RM572075 |

Plataforma que coleta automaticamente da **Wikipédia** as classificações e os artilheiros
das **5 principais ligas europeias** (Premier League, La Liga, Serie A, Bundesliga, Ligue 1)
e do **Brasileirão**, guarda tudo no **MongoDB**, disponibiliza os dados numa **API FastAPI**
e apresenta indicadores e gráficos num **dashboard web**.

```
Wikipédia  →  Web Crawler (Python)  →  MongoDB  →  API (FastAPI)  →  Dashboard (HTML/JS + Chart.js)
```

---

## 1. Estrutura do projeto

```
futebol-dados/
├── crawler/                 # COLETA: roda sozinho, sem depender da API
│   ├── ligas.py             #   ligas coletadas e como montar o título de cada página
│   ├── wikipedia.py         #   cliente HTTP (User-Agent, intervalo, novas tentativas)
│   ├── parser.py            #   lê o HTML e encontra as tabelas certas
│   ├── tratamento.py        #   limpa, valida e calcula campos derivados
│   └── main.py              #   ponto de entrada: python -m crawler.main
├── database/                # PERSISTÊNCIA
│   ├── conexao.py           #   conexão e índices únicos (evitam duplicatas)
│   └── repositorio.py       #   gravação com upsert + consultas e agregações
├── api/                     # API
│   ├── main.py              #   aplicação FastAPI (também serve o dashboard)
│   └── rotas.py             #   todos os endpoints /api/...
├── dashboard/               # INTERFACE
│   ├── index.html
│   ├── style.css
│   ├── app.js               #   busca os dados só pela API
│   └── vendor/chart.umd.min.js   # Chart.js local (funciona sem internet)
├── docs/                    # documentação pedida na entrega
│   ├── site_e_dados.md      #   descrição do site escolhido e dos dados coletados
│   ├── banco_de_dados.md    #   estrutura das coleções do MongoDB
│   └── endpoints.md         #   documentação dos endpoints
├── tests/                   # testes automatizados (sem internet e sem MongoDB)
├── config.py                # configurações (lidas do arquivo .env)
├── utils.py
├── requirements.txt
├── docker-compose.yml       # MongoDB via Docker (opcional)
└── .env.example
```

---

## 2. Pré-requisitos

| Ferramenta | Versão | Observação |
|---|---|---|
| Python | 3.10 ou mais nova | `python --version` |
| MongoDB | 6 ou mais novo | local, via Docker **ou** MongoDB Atlas (nuvem, gratuito) |
| Navegador | qualquer um atual | para abrir o dashboard |

**Escolha UMA forma de ter o MongoDB:**

- **Docker (mais simples se você já tem Docker):** na pasta do projeto, rode `docker compose up -d`.
- **Instalação local:** baixe o *MongoDB Community Server* em mongodb.com/try/download/community
  e instale com as opções padrão (no Windows, marque "Install MongoDB as a Service").
  Instale também o **MongoDB Compass** para ver os dados com interface gráfica.
- **MongoDB Atlas (nuvem):** crie um cluster gratuito, libere seu IP, copie a *connection string*
  (`mongodb+srv://...`) e coloque em `MONGO_URI` no arquivo `.env`.

---

## 3. Instalação (passo a passo)

```bash
# 1) Entre na pasta do projeto
cd futebol-dados

# 2) Crie e ative um ambiente virtual
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# 3) Instale as dependências
pip install -r requirements.txt

# 4) Crie o arquivo de configuração
# Windows:  copy .env.example .env
# Linux/macOS:
cp .env.example .env
```

Abra o `.env` e **troque o e-mail do `USER_AGENT`** pelo e-mail do grupo. A Wikipédia pede
que todo robô se identifique com um contato.

> Todos os comandos abaixo são executados **na pasta raiz do projeto** (`futebol-dados/`),
> com o ambiente virtual ativado.

---

## 4. Execução

### 4.1 Rodar o crawler (coleta)

```bash
python -m crawler.main
```

Por padrão ele coleta as 6 ligas **de 2015 até a temporada atual** de cada uma. Em outubro de 2026,
isso significa até a **2026-27** na Europa e o **Brasileirão 2026**, as duas em andamento.
São 72 páginas, com 1 segundo de intervalo entre elas (cerca de 1 a 2 minutos). A temporada atual
é calculada sozinha pela data: as ligas europeias começam em agosto e o Brasileirão em abril.
A saída é parecida com:

```
15:40:01 Execução 6523... iniciada: 6 liga(s), temporadas 2015 até a atual
15:40:02 OK  Premier League  2015-16  20 times, 20 artilheiros | campeão/líder: Leicester City
...
15:40:13 OK  Premier League  2026-27  20 times, 20 artilheiros | campeão/líder: ... (líder, temporada em andamento)
...
15:41:10 Fim da execução (concluida): 72 páginas, 1440 registros novos, 0 atualizados, 0 erro(s)
```

Outras formas de rodar:

```bash
python -m crawler.main --ligas brasileirao                 # só uma liga
python -m crawler.main --ligas premier-league la-liga      # algumas ligas
python -m crawler.main --inicio 2026                       # só a temporada atual (rápido)
python -m crawler.main --inicio 2020 --fim 2024            # outro período, só temporadas encerradas
python -m crawler.main --help                              # ajuda
```

Slugs das ligas: `premier-league`, `la-liga`, `serie-a`, `bundesliga`, `ligue-1`, `brasileirao`.

**Pode rodar quantas vezes quiser:** os registros existentes são atualizados (sem duplicar),
nada é apagado, e cada execução fica registrada na coleção `execucoes`.

**Temporada atual (em andamento):** a cada nova coleta, os pontos e as posições são atualizados.
O valor anterior também fica guardado no campo `historico` de cada time, então dá para ver a
evolução entre uma coleta e outra. Ela não tem campeão definido; o dashboard mostra o líder,
num painel "Temporada atual". Ela também fica de fora das médias de "Equilíbrio das ligas" e
do ranking de títulos, porque ainda não terminou.

### 4.2 Conferir os dados no MongoDB

No **Compass**, conecte em `mongodb://localhost:27017` e abra o banco `futebol_dados`.
Ou pelo terminal com `mongosh`:

```javascript
use futebol_dados
db.classificacoes.countDocuments()
db.classificacoes.findOne({ liga: "brasileirao", posicao: 1 })
db.temporadas.find({}, { liga: 1, temporada: 1, campeao: 1, _id: 0 }).sort({ ano_inicio: -1 })
db.execucoes.find().sort({ inicio: -1 }).limit(1)
```

### 4.3 Subir a API

```bash
uvicorn api.main:app --reload
```

- Documentação interativa (Swagger): **http://localhost:8000/docs**
- Exemplo: http://localhost:8000/api/estatisticas/resumo

### 4.4 Abrir o dashboard

Com a API rodando, acesse **http://localhost:8000/dashboard/** (ou só http://localhost:8000).

O dashboard é HTML/CSS/JavaScript puro e busca **todos** os dados nos endpoints da API.

### 4.5 Rodar os testes (opcional)

```bash
python -m pytest -q
```

Os testes usam HTML de exemplo no formato da Wikipédia e um MongoDB simulado (mongomock),
então funcionam sem internet e sem MongoDB instalado.

---

## 5. Roteiro sugerido para a apresentação

1. **Mostrar o site:** abra uma página, por exemplo `https://en.wikipedia.org/wiki/2026_Campeonato_Brasileiro_Série_A`,
   e mostre a tabela de classificação e a de artilheiros.
2. **Rodar o crawler** ao vivo com algo rápido: `python -m crawler.main --ligas brasileirao --inicio 2022 --fim 2024`.
   Explique o log (página baixada, times e artilheiros extraídos).
3. **Mostrar o MongoDB** no Compass: um documento de `classificacoes` com os campos `fonte`
   (de onde veio) e `coleta` (quando veio).
4. **Rodar o crawler de novo** com o mesmo comando e mostrar que a contagem **não mudou**, que
   `coleta.total_coletas` subiu para 2 e que `primeira_coleta` foi mantida (sem duplicar, sem apagar).
5. **Temporada atual:** rode `python -m crawler.main --inicio 2026` e mostre, num time do Brasileirão
   2026, o campo `historico` com um retrato por coleta. Se houver rodada nova entre uma coleta e
   outra, os pontos mudam e o valor antigo continua guardado.
6. **Mostrar a API** em `/docs`: execute `/api/classificacoes` com filtro, `/api/classificacoes/{id}`
   e `/api/estatisticas/resumo`.
7. **Mostrar o dashboard:** indicadores, gráficos, filtro por liga, busca de um time (gráfico de trajetória)
   a tabela com ordenação e paginação e o painel "Temporada atual".

> Dica: rode a coleta completa **antes** da apresentação, para o dashboard já estar cheio,
> e use a coleta pequena do passo 2 só para demonstrar.

---

## 6. Problemas comuns

| Sintoma | Causa provável e solução |
|---|---|
| `ServerSelectionTimeoutError` | O MongoDB não está rodando. Inicie o serviço ou `docker compose up -d`. |
| `ModuleNotFoundError: crawler` | Rode os comandos na pasta raiz do projeto e use `python -m crawler.main` (com `-m`). |
| Dashboard mostra "Não foi possível conectar à API" | Suba a API com `uvicorn api.main:app --reload` e abra pelo endereço `http://localhost:8000/dashboard/`. |
| Dashboard mostra "O banco está vazio" | Rode o crawler antes. |
| Log com `página não existe na Wikipédia` | A página daquela temporada ainda não existe ou mudou de nome. Confira o título na Wikipédia. |
| Log com `tabela de classificação não encontrada` | O formato daquela página é diferente. A coleta continua com as outras páginas; veja o erro em `db.execucoes`. |
| Erro 403/429 da Wikipédia | Confira se o `USER_AGENT` tem um contato válido e aumente `INTERVALO_REQUISICOES` no `.env`. |

---

## 7. Tecnologias

Python, Requests, BeautifulSoup + lxml (crawler) · MongoDB + PyMongo (persistência) ·
FastAPI + Uvicorn (API) · HTML, CSS, JavaScript e Chart.js (dashboard) · Pytest + mongomock (testes).

Documentação detalhada em [`docs/`](docs/).
