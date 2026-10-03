"""Orquestrador: coordena o fluxo completo de uma mensagem.

Usuário -> Guardrail de entrada -> Roteador -> Especialista -> Juiz -> (refaz se reprovado)
        -> Guardrail de saída -> memória da sessão -> Usuário
"""
from app.config import MAX_TENTATIVAS_JUIZ
from app.core.analista import agente_analista
from app.core.faq import agente_faq
from app.core.juiz import julgar
from app.core.memory import get_session_history
from app.core.recomendador import AVISO, agente_recomendador
from app.core.roteador import rotear
from app.guardrails.guardrails import guardrail_entrada, guardrail_saida
from app.schemas.agentes import RespostaEspecialista, Resultado

FORA_ESCOPO = (
    "Esse assunto está fora do meu escopo. Posso ajudar com dúvidas gerais sobre o sistema, "
    "análises descritivas dos dados da empresa e percepções/insights sobre eles."
)

RESPOSTA_REPROVADA = (
    "Não consegui gerar uma resposta confiável para essa pergunta com os dados disponíveis. "
    "Pode reformular ou detalhar um pouco mais?"
)

ESPECIALISTAS = {
    "faq": agente_faq,
    "analista": agente_analista,
    "recomendador": agente_recomendador,
}


class Orquestrador:
    def __init__(self, session_id: str):
        self.session_id = session_id

    @property
    def historico(self):
        return get_session_history(self.session_id)

    def processar(self, mensagem: str) -> Resultado:
        passos: list[str] = []

        # 1) Guardrail de entrada
        g_in = guardrail_entrada(mensagem)
        if not g_in.permitido:
            passos.append(f"guardrail_entrada: BLOQUEADO ({g_in.motivo})")
            return Resultado(resposta=g_in.motivo, rota="bloqueado", passos=passos)
        pergunta = g_in.texto
        passos.append("guardrail_entrada: ok")

        historico = self.historico.messages

        # 2) Roteador
        decisao = rotear(pergunta, historico)
        passos.append(f"roteador: {decisao.rota} ({decisao.motivo})")

        if decisao.rota == "fora_escopo":
            resposta, aprovado = FORA_ESCOPO, True
        else:
            # 3) Especialista + 4) Juiz (com nova tentativa se reprovado)
            especialista = ESPECIALISTAS[decisao.rota]
            entrada, aprovado = pergunta, False
            saida = RespostaEspecialista(resposta="")
            for tentativa in range(MAX_TENTATIVAS_JUIZ + 1):
                saida = especialista(entrada, historico)
                veredito = julgar(pergunta, saida.resposta, saida.contexto, decisao.rota)
                passos.append(
                    f"juiz (tentativa {tentativa + 1}): aprovado={veredito.aprovado} "
                    f"nota={veredito.nota} - {veredito.motivo}"
                )
                if veredito.aprovado:
                    aprovado = True
                    break
                # Feedback do juiz volta para o especialista
                entrada = (
                    f"{pergunta}\n\n[Revisão interna - corrija a resposta anterior. "
                    f"Problema apontado: {veredito.motivo}]"
                )
            resposta = saida.resposta if aprovado else RESPOSTA_REPROVADA

        if decisao.rota == "recomendador" and aprovado:
            resposta = f"{resposta}\n\n{AVISO}"

        # 5) Guardrail de saída
        resposta = guardrail_saida(resposta).texto
        passos.append("guardrail_saida: ok")

        # 6) Memória da sessão (pergunta já higienizada + resposta final)
        self.historico.add_user_message(pergunta)
        self.historico.add_ai_message(resposta)

        return Resultado(resposta=resposta, rota=decisao.rota, passos=passos)
