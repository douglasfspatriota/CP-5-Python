"""
Gera HTML no mesmo formato das páginas de temporada da Wikipédia,
para testar o parser e o crawler sem acessar a internet.
"""


def _linha_time(pos, nome, j, v, e, d, gp, gc, pts, marcador="", qualif=None):
    saldo = gp - gc
    saldo_txt = f"+{saldo}" if saldo > 0 else ("0" if saldo == 0 else f"−{abs(saldo)}")
    marc = f' <span style="font-weight:bold">({marcador})</span>' if marcador else ""
    qual = f'<td rowspan="{qualif[0]}">{qualif[1]}</td>' if qualif else ""
    return (
        f'<tr><td style="text-align:center">{pos}</td>'
        f'<th scope="row" style="text-align:left"><span class="flagicon"><img alt="X"></span>'
        f'<a href="/wiki/x">{nome}</a>{marc}</th>'
        f"<td>{j}</td><td>{v}</td><td>{e}</td><td>{d}</td><td>{gp}</td><td>{gc}</td>"
        f'<td>{saldo_txt}</td><td><b>{pts}</b><sup class="reference">[a]</sup></td>{qual}</tr>'
    )


def gerar_pagina(times: list[tuple], artilheiros: list[tuple], titulo="Liga") -> str:
    """
    times: (nome, v, e, d, gp, gc, marcador)   — já na ordem da classificação
    artilheiros: (jogador, clube, gols)        — em ordem decrescente de gols
    """
    n = len(times)
    linhas = []
    for i, (nome, v, e, d, gp, gc, marc) in enumerate(times, start=1):
        qualif = (4, "Qualification for the Champions League") if i == 1 else None
        if i == 5:
            qualif = (n - 7, "")
        if i == n - 2:
            qualif = (3, "Relegation to the second division")
        linhas.append(_linha_time(i, nome, v + e + d, v, e, d, gp, gc, 3 * v + e, marc, qualif))

    # Tabela de artilheiros com rowspan para empates (como na Wikipédia)
    art_html = []
    i = 0
    while i < len(artilheiros):
        grupo = [a for a in artilheiros[i:] if a[2] == artilheiros[i][2]]
        for k, (jog, clube, gols) in enumerate(grupo):
            if k == 0:
                rs = f' rowspan="{len(grupo)}"' if len(grupo) > 1 else ""
                art_html.append(f'<tr><td{rs}>{i + 1}</td><td><span class="flagicon"><img alt="BRA"></span> '
                                f'<a>{jog}</a></td><td>{clube}</td><td{rs}>{gols}</td></tr>')
            else:
                art_html.append(f'<tr><td><span class="flagicon"></span> <a>{jog}</a></td><td>{clube}</td></tr>')
        i += len(grupo)

    rodadas = "".join(f"<th>{r}</th>" for r in range(1, 6))
    return f"""
<div class="mw-parser-output">
<p>The {titulo} season...</p>
<div class="mw-heading mw-heading2"><h2 id="Teams">Teams</h2></div>
<table class="wikitable"><tbody><tr><th>Team</th><th>Location</th><th>Stadium</th><th>Capacity</th></tr>
<tr><td>Time A</td><td>Cidade</td><td>Estádio</td><td>40,000</td></tr></tbody></table>
<div class="mw-heading mw-heading2"><h2 id="League_table">League table</h2></div>
<table class="wikitable" style="text-align:center;"><tbody>
<tr><th scope="col"><abbr title="Position">Pos</abbr></th><th scope="col">Team
<span class="sortkey" style="display:none">!</span></th>
<th scope="col"><abbr title="Played">Pld</abbr></th><th scope="col"><abbr title="Won">W</abbr></th>
<th scope="col"><abbr title="Drawn">D</abbr></th><th scope="col"><abbr title="Lost">L</abbr></th>
<th scope="col"><abbr title="Goals for">GF</abbr></th><th scope="col"><abbr title="Goals against">GA</abbr></th>
<th scope="col"><abbr title="Goal difference">GD</abbr></th><th scope="col"><abbr title="Points">Pts</abbr></th>
<th scope="col">Qualification or relegation</th></tr>
{''.join(linhas)}
</tbody></table>
<div class="mw-heading mw-heading3"><h3 id="Positions_by_round">Positions by round</h3></div>
<table class="wikitable"><tbody><tr><th>Team \\ Round</th>{rodadas}</tr>
<tr><td>Time A</td><td>1</td><td>1</td><td>2</td><td>1</td><td>1</td></tr></tbody></table>
<div class="mw-heading mw-heading2"><h2 id="Season_statistics">Season statistics</h2></div>
<div class="mw-heading mw-heading3"><h3 id="Hat-tricks">Hat-tricks</h3></div>
<table class="wikitable"><tbody><tr><th>Player</th><th>For</th><th>Against</th><th>Result</th></tr>
<tr><td>Fulano</td><td>A</td><td>B</td><td>4–0</td></tr></tbody></table>
<div class="mw-heading mw-heading3"><h3 id="Top_scorers">Top scorers</h3></div>
<table class="wikitable"><tbody><tr><th>Rank</th><th>Player</th><th>Club</th><th>Goals<sup>[1]</sup></th></tr>
{''.join(art_html)}
</tbody></table>
<div class="mw-heading mw-heading3"><h3 id="Clean_sheets">Clean sheets</h3></div>
<table class="wikitable"><tbody><tr><th>Rank</th><th>Player</th><th>Club</th><th>Clean sheets</th></tr>
<tr><td>1</td><td>Goleiro</td><td>Time</td><td>15</td></tr></tbody></table>
</div>"""
