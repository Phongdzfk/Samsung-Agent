"""LLM-as-a-Judge với ĐÚNG prompt chính thức của LongMemEval (src/evaluation/evaluate_qa.py).

Không sửa prompt: đổi prompt chấm giữa chừng là mọi số đo trước đó mất giá trị so sánh.
Nhãn = 'yes' in câu trả lời (như script gốc).
"""
from __future__ import annotations

from ..adapters.llm import BaseLLM

_BASE = ("I will give you a question, a correct answer, and a response from a model. Please answer "
         "yes if the response contains the correct answer. Otherwise, answer no. If the response is "
         "equivalent to the correct answer or contains all the intermediate steps to get the correct "
         "answer, you should also answer yes. If the response only contains a subset of the "
         "information required by the answer, answer no. ")

TEMPLATES = {
    "default": _BASE + "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                       "Is the model response correct? Answer yes or no only.",
    "temporal-reasoning": _BASE + "In addition, do not penalize off-by-one errors for the number "
        "of days. If the question asks for the number of days/weeks/months, etc., and the model "
        "makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the model's "
        "response is still correct. \n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}"
        "\n\nIs the model response correct? Answer yes or no only.",
    "knowledge-update": "I will give you a question, a correct answer, and a response from a "
        "model. Please answer yes if the response contains the correct answer. Otherwise, answer "
        "no. If the response contains some previous information along with an updated answer, the "
        "response should be considered as correct as long as the updated answer is the required "
        "answer.\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model "
        "response correct? Answer yes or no only.",
    "single-session-preference": "I will give you a question, a rubric for desired personalized "
        "response, and a response from a model. Please answer yes if the response satisfies the "
        "desired response. Otherwise, answer no. The model does not need to reflect all the points "
        "in the rubric. The response is correct as long as it recalls and utilizes the user's "
        "personal information correctly.\n\nQuestion: {}\n\nRubric: {}\n\nModel Response: {}\n\n"
        "Is the model response correct? Answer yes or no only.",
    "abstention": "I will give you an unanswerable question, an explanation, and a response from a "
        "model. Please answer yes if the model correctly identifies the question as unanswerable. "
        "The model could say that the information is incomplete, or some other information is "
        "given but the asked information is not.\n\nQuestion: {}\n\nExplanation: {}\n\nModel "
        "Response: {}\n\nDoes the model correctly identify the question as unanswerable? Answer "
        "yes or no only.",
}


def judge_prompt(qtype: str, question: str, gold: str, hypothesis: str, is_abs: bool) -> str:
    if is_abs:
        t = TEMPLATES["abstention"]
    elif qtype in ("single-session-user", "single-session-assistant", "multi-session"):
        t = TEMPLATES["default"]
    elif qtype in TEMPLATES:
        t = TEMPLATES[qtype]
    else:
        raise NotImplementedError(qtype)
    return t.format(question, gold, hypothesis)


def judge(llm: BaseLLM, qtype: str, question: str, gold: str, hypothesis: str, is_abs: bool,
          trial: int = 0) -> tuple[bool, str]:
    raw = llm.complete_text(judge_prompt(qtype, question, gold, hypothesis, is_abs),
                            role="judge", salt=f"judge-trial-{trial}" if trial else "")
    return "yes" in raw.lower(), raw.strip()
