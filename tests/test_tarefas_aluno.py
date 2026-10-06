"""TAREFA DO ALUNO -- os cinco testes que faltam para os >= 8 do entregavel.

Nenhum deles precisa de banco: os tres primeiros rodam so contra o motor.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from app.dominio.motor_emergia import SEIS_CASAS, calcular_indices

TOLERANCIA = Decimal("1E-6")


def test_regressao_numerica_contra_a_planilha(fluxos_golden):
    """Compara os seis indices com a aba SSB da Planilha_base.xlsx.

    Criterio do entregavel: abs(delta) <= 1E-6 por indice. Comece pelo inventario
    de referencia (Y = 200, F = 50, renovaveis = 115, nao renovaveis = 85) e
    escreva os seis valores esperados a mao antes de rodar -- se o teste passar
    de primeira sem voce saber o valor esperado, ele nao esta provando nada.
    """
    # Derivados a mao a partir de Y = 200, F = 50, renov. = 115, nao renov. = 85:
    #   EYR = Y / F             = 200 / 50          = 4
    #   ELR = nao renov./renov. = 85 / 115          = 0.7391304347...
    #   ESI = EYR / ELR         = 4 * 115 / 85      = 5.4117647058...
    #   EII = ELR / EYR         = 85 / 460          = 0.1847826086...
    #   %R  = renov. / Y * 100  = 115 / 200 * 100   = 57.5
    esperado = {
        "y": Decimal("200.000000"),
        "eyr": Decimal("4.000000"),
        "elr": Decimal("0.739130"),
        "esi": Decimal("5.411765"),
        "eii": Decimal("0.184783"),
        "percentual_r": Decimal("57.500000"),
    }
    indices = calcular_indices(fluxos_golden, Decimal("1000"))
    for nome, valor in esperado.items():
        obtido = getattr(indices, nome)
        assert isinstance(obtido, Decimal), nome
        assert abs(obtido - valor) <= TOLERANCIA, f"{nome}: {obtido} != {valor}"


def test_quantizacao_unica_no_final():
    """Mostra o erro duplo de arredondar no meio do calculo.

    Calcule ESI = EYR / ELR de duas formas: (a) quantizando EYR e ELR para seis
    casas antes de dividir; (b) dividindo em 28 digitos e quantizando so o ESI.
    Os dois resultados diferem -- e o motor usa (b). Prove a diferenca.
    """
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_EVEN
        eyr = Decimal(200) / Decimal(50)
        elr = Decimal(85) / Decimal(115)

        # (a) arredonda no meio: ELR perde 0.0000004347..., e a divisao amplifica
        esi_a = (eyr.quantize(SEIS_CASAS) / elr.quantize(SEIS_CASAS)).quantize(SEIS_CASAS)
        # (b) uma unica quantizacao, no final
        esi_b = (eyr / elr).quantize(SEIS_CASAS)

    assert esi_a == Decimal("5.411768")
    assert esi_b == Decimal("5.411765")
    assert esi_a != esi_b
    assert abs(esi_a - esi_b) > TOLERANCIA     # (a) estoura a tolerancia do entregavel


def test_ordem_da_soma_com_magnitudes_divergentes():
    """A associatividade quebra quando as magnitudes divergem.

    Monte um inventario com um fluxo de 1E20 sej e outro de 1E-5 sej e some nas
    duas ordens possiveis. Explique, no corpo do teste, por que a precisao de 28
    digitos e o limite -- e por que ordenar o inventario e uma decisao de dominio.
    """
    grande = Decimal("1E20")
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_EVEN

        # 1E20 + 1E-5 ocupa 21 digitos inteiros + 5 decimais = 26 digitos significativos.
        # Cabe nos 28: a soma e exata e a ordem nao importa.
        pequeno = Decimal("1E-5")
        assert grande + pequeno == pequeno + grande
        assert (grande + pequeno) - grande == pequeno

        # Dois fluxos sozinhos nunca dependem da ordem (a + b == b + a). O que quebra e
        # a associatividade com tres ou mais: com 4E-8, a soma pediria 29 digitos -- um
        # alem do limite -- e o pequeno e arredondado para zero ao encostar no grande.
        minusculo = Decimal("4E-8")
        assert grande + minusculo == grande                  # absorvido

        inventario = [grande] + [minusculo] * 1000
        grande_primeiro = sum(inventario, Decimal(0))
        pequenos_primeiro = sum(reversed(inventario), Decimal(0))

    # Grande primeiro: cada 4E-8 some sozinho, mil vezes. Pequenos primeiro: eles se
    # acumulam em 4E-5, que cabe nos 28 digitos ao lado de 1E20.
    assert grande_primeiro == grande
    assert pequenos_primeiro == grande + Decimal("4E-5")
    assert grande_primeiro != pequenos_primeiro

    # Por isso ordenar o inventario (ex.: por magnitude crescente) e decisao de dominio:
    # com magnitudes que estouram 28 digitos, a mesma lista em outra ordem da outro Y,
    # e o determinismo sob permutacao deixa de valer. Com sej reais (1E12 a 1E20) e
    # fluxos de mesma ordem de grandeza, 28 digitos sobram -- o golden nao e afetado.


def test_erro_de_dominio_responde_problem_json(cliente, corpo_golden):
    """Inventario sem fluxo renovavel deve sair 422 em application/problem+json.

    Hoje sai 500, porque o handler de FluxosInsuficientes nao existe -- note que
    o 404 e o 422 do framework JA saem no formato certo, pelos handlers do
    esqueleto: o que falta e so o erro de dominio. Feche o TODO PASSO 3 em
    app/main.py e depois assegure aqui: status 422, header content-type
    application/problem+json e os cinco campos da RFC 9457.
    """
    corpo_golden["fluxos"] = [f for f in corpo_golden["fluxos"]
                              if f["categoria"] in ("N", "MN")]
    r = cliente.post("/v1/safras/42/calculos", json=corpo_golden)

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    corpo = r.json()
    for campo in ("type", "title", "status", "detail", "instance"):
        assert campo in corpo
    assert corpo["type"].endswith("/fluxos-insuficientes")
    assert corpo["status"] == 422
    assert "renovavel" in corpo["detail"]


def test_campo_extra_no_corpo_da_requisicao_e_rejeitado(cliente, corpo_golden):
    """"energia_produto_jj" tem de morrer com 422, nao virar calculo incompleto.

    Hoje o CalculoRequestDTO nao declara extra="forbid": o campo desconhecido e
    ignorado e o typo passa silencioso, exatamente como na planilha. Feche o
    TODO PASSO 3 em app/api/v1/dto.py e prove aqui.
    """
    corpo_golden["energia_produto_jj"] = "1000"
    r = cliente.post("/v1/safras/42/calculos", json=corpo_golden)

    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    campos = [e["campo"] for e in r.json()["erros"]]
    assert "body.energia_produto_jj" in campos
