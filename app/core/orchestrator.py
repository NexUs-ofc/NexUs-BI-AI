"""Orchestrator agent: coordinates the full flow of one message.

Question -> Input guardrail -> Router -> Specialist -> Judge -> (retry if rejected)
         -> Output guardrail -> session memory -> Answer
"""
from app.config import MAX_JUDGE_RETRIES
from app.core.analyst import analyst_agent
from app.core.faq import faq_agent
from app.core.judge import judge
from app.core.memory import get_session_history
from app.core.recommender import recommender_agent
from app.core.router import route
from app.guardrails.guardrails import input_guardrail, output_guardrail
from app.prompts.orchestrator import JUDGE_REVISION, OUT_OF_SCOPE_ANSWER, REJECTED_ANSWER
from app.prompts.recommender import RECOMMENDER_DISCLAIMER
from app.schemas.agents import Result, SpecialistAnswer

SPECIALISTS = {
    "faq": faq_agent,
    "analyst": analyst_agent,
    "recommender": recommender_agent,
}


class Orchestrator:
    def __init__(self, session_id: str):
        self.session_id = session_id

    @property
    def history(self):
        return get_session_history(self.session_id)

    def process(self, message: str) -> Result:
        steps: list[str] = []

        # 1) Input guardrail
        guard_in = input_guardrail(message)
        if not guard_in.allowed:
            steps.append(f"input_guardrail: BLOCKED ({guard_in.reason})")
            return Result(answer=guard_in.reason, route="blocked", steps=steps)
        question = guard_in.text
        steps.append("input_guardrail: ok")

        history = self.history.messages

        # 2) Router
        decision = route(question, history)
        steps.append(f"router: {decision.route} ({decision.reason})")

        if decision.route == "out_of_scope":
            answer, approved = OUT_OF_SCOPE_ANSWER, True
        else:
            # TODO: once the database tools are defined, fetch the data here and
            # pass it to analyst_agent / recommender_agent (parameter `data`).
            specialist = SPECIALISTS[decision.route]

            # 3) Specialist + 4) Judge (retries if rejected)
            current_input, approved = question, False
            output = SpecialistAnswer(answer="")
            for attempt in range(MAX_JUDGE_RETRIES + 1):
                output = specialist(current_input, history)
                verdict = judge(question, output.answer, output.context, decision.route)
                steps.append(
                    f"judge (attempt {attempt + 1}): approved={verdict.approved} "
                    f"score={verdict.score} - {verdict.reason}"
                )
                if verdict.approved:
                    approved = True
                    break
                current_input = JUDGE_REVISION.format(question=question, reason=verdict.reason)
            answer = output.answer if approved else REJECTED_ANSWER

        if decision.route == "recommender" and approved:
            answer = f"{answer}\n\n{RECOMMENDER_DISCLAIMER}"

        # 5) Output guardrail
        answer = output_guardrail(answer).text
        steps.append("output_guardrail: ok")

        # 6) Session memory (sanitized question + final answer)
        self.history.add_user_message(question)
        self.history.add_ai_message(answer)

        return Result(answer=answer, route=decision.route, steps=steps)
