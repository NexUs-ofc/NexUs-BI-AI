"""Recomendações concretas PARA O APP, ligadas aos números do mês.

São regras em código (não o LLM): cada ação cita o número que a motivou, e esse número vem de `dados`,
então texto e gráfico nunca divergem. A narrativa dos agentes cuida da leitura de negócio; aqui ficam as
mudanças de produto que o NexUs pode fazer.

    alerta_pos_vencimento   descartes esquecidos (mais de 7 dias após vencer) -> avisar quando passar da validade
    lembrete_perecivel      categorias que lideram o desperdício do mês        -> lembrete de consumo antes do prazo
    cadastro_validade       itens sem validade na despensa                     -> tornar a validade obrigatória
    alerta_vence_7d         itens que vencem em 7 dias (só com foto)           -> destacar "consumir primeiro"
    reposicao_minimo        casas abaixo do mínimo (só com foto)               -> lista de compras sugerida
"""
from report_generator.formatting import br, integer, pct
from report_generator.schemas import AcaoApp, Dados

TOP_CATEGORIAS = 3
MIN_CATEGORIAS_PARA_LEMBRETE = 1


def _lista(nomes: list[str]) -> str:
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _fora(dados: Dados, codigo: str) -> bool:
    k = dados.kpis.get(codigo)
    return bool(k and k.valor is not None and k.meta is not None and k.valor > k.meta)


def acoes_app(dados: Dados) -> list[AcaoApp]:
    acoes: list[AcaoApp] = []

    # 1) Alerta pós-vencimento: o descarte "esquecido" mostra que o aviso chega tarde ou nem chega
    d2 = dados.kpis.get("D2")
    if d2 and d2.valor is not None and d2.valor > 0:
        acoes.append(AcaoApp(
            id="alerta_pos_vencimento", prioridade=1,
            titulo="Avisar quando o item passar da validade",
            texto=("Enviar uma notificação no dia em que o item vence e repetir 3 dias depois, com o botão "
                   "\"descartar\" ou \"ainda está bom\". Hoje muitos itens ficam esquecidos até o descarte."),
            evidencia=f"{pct(d2.valor)} das unidades descartadas com validade foram descartadas mais de 7 dias "
                      f"depois de vencer."))

    # 2) Lembrete para as categorias que mais desperdiçam no mês
    lideres = [c for c in dados.desperdicio_categoria if c.unidades_descartadas > 0][:TOP_CATEGORIAS]
    if len(lideres) >= MIN_CATEGORIAS_PARA_LEMBRETE:
        nomes = [c.categoria for c in lideres]
        total = sum(c.pct_do_desperdicio or 0 for c in lideres)
        acoes.append(AcaoApp(
            id="lembrete_perecivel", prioridade=1,
            titulo=f"Lembrete de consumo para {_lista(nomes)}",
            texto=(f"Criar um lembrete automático \"consumir primeiro\" para {_lista(nomes)}, que são as categorias "
                   "perecíveis que mais viram descarte, disparado 2 dias antes da validade."),
            evidencia=f"{_lista(nomes)} somam {pct(total)} das unidades descartadas no mês "
                      f"({br(lideres[0].d9_indice, 2)} unidades descartadas por casa em {lideres[0].categoria})."))

    # 3) Cadastro de validade (estado: só com foto da despensa)
    d8 = dados.kpis.get("D8")
    if dados.tem_despensa and _fora(dados, "D8"):
        acoes.append(AcaoApp(
            id="cadastro_validade", prioridade=2,
            titulo="Tornar a validade obrigatória no cadastro",
            texto=("Pedir a validade ao cadastrar o item (com leitura da embalagem pela câmera ou sugestão de "
                   "prazo padrão por categoria) para que o item possa gerar alertas."),
            evidencia=f"{pct(d8.valor)} das unidades na despensa estão sem validade (meta: até {pct(d8.meta)})."))

    d4 = dados.kpis.get("D4")
    if dados.tem_despensa and _fora(dados, "D4"):
        acoes.append(AcaoApp(
            id="alerta_vence_7d", prioridade=2,
            titulo="Destacar o que vence em 7 dias na tela inicial",
            texto="Mostrar uma lista \"consumir primeiro\" com os itens que vencem na semana, com sugestão de receita.",
            evidencia=f"{pct(d4.valor)} das unidades com validade vencem em até 7 dias (limite: {pct(d4.meta)})."))

    d6 = dados.kpis.get("D6")
    if dados.tem_despensa and _fora(dados, "D6"):
        acoes.append(AcaoApp(
            id="reposicao_minimo", prioridade=3,
            titulo="Sugerir lista de compras quando o estoque ficar abaixo do mínimo",
            texto="Montar a lista de compras automaticamente com os itens abaixo do mínimo configurado.",
            evidencia=f"{pct(d6.valor)} das casas com mínimo configurado têm algum item abaixo dele "
                      f"(meta: até {pct(d6.meta)})."))

    d1 = dados.kpis.get("D1")
    if d1 and d1.valor is not None and d1.meta is not None and d1.valor > d1.meta and dados.resumo:
        acoes.append(AcaoApp(
            id="resumo_semanal", prioridade=3,
            titulo="Enviar um resumo semanal do desperdício",
            texto="Mostrar à família quanto foi descartado na semana e qual categoria mais pesou.",
            evidencia=f"A taxa de desperdício do mês foi {pct(d1.valor)}, acima da meta de {pct(d1.meta)} "
                      f"({integer(dados.resumo.unidades_descartadas)} de "
                      f"{integer(dados.resumo.unidades_saidas)} unidades)."))

    return sorted(acoes, key=lambda a: a.prioridade)
