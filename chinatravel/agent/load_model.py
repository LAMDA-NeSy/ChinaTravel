import re
import os
from dataclasses import dataclass
from typing import Any


_METHOD_MODIFIER_RE = re.compile(
    r"_(?:\d+steps|oracle_?translation|preference_?search)$"
)


def normalize_run_name(value):
    text = str(value or "model")
    text = re.sub(r"[^0-9A-Za-z_.-]+", "_", text)
    return text.strip("_") or "model"


def resolve_llm_name(llm_name=None):
    value = llm_name or os.getenv("CHINATRAVEL_OPENAI_MODEL") or os.getenv("OPENAI_MODEL")
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def resolve_agent_llm_name(agent_name, llm_name=None):
    if agent_name == "RuleNeSy" and llm_name is None:
        return "rule"
    return resolve_llm_name(llm_name)


def method_has_language(method, lang):
    base = str(method)
    while True:
        match = _METHOD_MODIFIER_RE.search(base)
        if match is None:
            break
        base = base[: match.start()]
    return base.endswith("_{}".format(lang))


def ensure_method_language(method, lang):
    method = str(method)
    if lang != "en" or method_has_language(method, lang):
        return method

    base = method
    modifiers = []
    while True:
        match = _METHOD_MODIFIER_RE.search(base)
        if match is None:
            break
        modifiers.insert(0, match.group(0))
        base = base[: match.start()]
    return "{}_en{}".format(base, "".join(modifiers))


def build_method_name(
    agent_name,
    llm_name=None,
    *,
    lang="zh",
    oracle_translation=False,
    preference_search=False,
    refine_steps=None,
):
    method = f"{agent_name}_{normalize_run_name(resolve_llm_name(llm_name))}"
    if lang == "en":
        method += "_en"
    if agent_name == "LLM-modulo" and refine_steps is not None:
        method += f"_{refine_steps}steps"
    if oracle_translation:
        method += "_oracletranslation"
    if preference_search:
        method += "_preferencesearch"
    return method


@dataclass(frozen=True)
class AgentRuntime:
    method: str
    result_dir: str
    log_dir: str
    cache_dir: str
    agent: Any


def build_run_dirs(project_root_path, method):
    result_dir = os.path.join(project_root_path, "results", method)
    cache_dir = os.path.join(project_root_path, "cache")
    log_dir = os.path.join(cache_dir, method)
    os.makedirs(result_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    return result_dir, log_dir, cache_dir


def create_agent_runtime(
    agent_name,
    llm_name,
    *,
    project_root_path,
    lang="zh",
    oracle_translation=False,
    preference_search=False,
    refine_steps=None,
    debug=True,
):
    from chinatravel.environment.world_env import WorldEnv

    method = build_method_name(
        agent_name,
        llm_name,
        lang=lang,
        oracle_translation=oracle_translation,
        preference_search=preference_search,
        refine_steps=refine_steps,
    )
    result_dir, log_dir, cache_dir = build_run_dirs(project_root_path, method)
    kwargs = {
        "method": agent_name,
        "env": WorldEnv(lang=lang),
        "backbone_llm": init_llm(llm_name),
        "cache_dir": cache_dir,
        "log_dir": log_dir,
        "debug": debug,
        "refine_steps": refine_steps,
        "lang": lang,
    }
    return AgentRuntime(
        method=method,
        result_dir=result_dir,
        log_dir=log_dir,
        cache_dir=cache_dir,
        agent=init_agent(kwargs),
    )


def _build_rule_nesy(kwargs):
    from .nesy_agent.rule_driven_rec import RuleDrivenAgent

    return RuleDrivenAgent(
        env=kwargs["env"],
        backbone_llm=kwargs["backbone_llm"],
        cache_dir=kwargs["cache_dir"],
        debug=kwargs["debug"],
    )


def _build_llm_nesy(kwargs):
    from .nesy_agent.llm_driven_rec import LLMDrivenAgent

    return LLMDrivenAgent(**kwargs)


def _react_prompt(kwargs, zero_shot=False):
    from .pure_neuro_agent import prompts as zh_prompts

    llm_name = kwargs["backbone_llm"].name.lower()
    if zero_shot:
        if "glm4" in llm_name:
            return zh_prompts.ZEROSHOT_REACT_INSTRUCTION_GLM4
        return zh_prompts.ZEROSHOT_REACT_INSTRUCTION

    if kwargs.get("lang", "zh") == "en":
        from .pure_neuro_agent.prompts.prompts_en import ONESHOT_REACT_INSTRUCTION

        return ONESHOT_REACT_INSTRUCTION

    if "glm4" in llm_name:
        return zh_prompts.ONESHOT_REACT_INSTRUCTION_GLM4
    return zh_prompts.ONESHOT_REACT_INSTRUCTION


def _build_act(kwargs):
    from .pure_neuro_agent.pure_neuro_agent import ActAgent
    from .pure_neuro_agent.prompts import ZEROSHOT_ACT_INSTRUCTION

    return ActAgent(
        env=kwargs["env"],
        backbone_llm=kwargs["backbone_llm"],
        prompt=ZEROSHOT_ACT_INSTRUCTION,
    )


def _build_react(kwargs):
    from .pure_neuro_agent.pure_neuro_agent import ReActAgent

    return ReActAgent(
        env=kwargs["env"],
        backbone_llm=kwargs["backbone_llm"],
        prompt=_react_prompt(kwargs),
    )


def _build_react_zero_shot(kwargs):
    from .pure_neuro_agent.pure_neuro_agent import ReActAgent

    return ReActAgent(
        env=kwargs["env"],
        backbone_llm=kwargs["backbone_llm"],
        prompt=_react_prompt(kwargs, zero_shot=True),
    )


def _build_llm_modulo(kwargs):
    from .nesy_verifier import LLMModuloAgent

    agent_kwargs = dict(kwargs)
    agent_kwargs["model"] = kwargs["backbone_llm"]
    agent_kwargs["max_steps"] = kwargs["refine_steps"]
    return LLMModuloAgent(**agent_kwargs)


def _build_tpc_agent(kwargs):
    from .tpc_agent.tpc_agent import TPCAgent

    return TPCAgent(**kwargs)


def _build_urbantrip(kwargs):
    from .UrbanTrip.tpc_agent import UrbanTrip

    return UrbanTrip(**kwargs)


AGENT_BUILDERS = {
    "RuleNeSy": _build_rule_nesy,
    "LLMNeSy": _build_llm_nesy,
    "Act": _build_act,
    "ReAct": _build_react,
    "ReAct0": _build_react_zero_shot,
    "LLM-modulo": _build_llm_modulo,
    "TPCAgent": _build_tpc_agent,
    "UrbanTrip": _build_urbantrip,
}


def init_agent(kwargs):
    method = kwargs["method"]
    try:
        builder = AGENT_BUILDERS[method]
    except KeyError as exc:
        raise ValueError(f"Unsupported agent method: {method}") from exc
    return builder(kwargs)


def init_llm(llm_name):
    from .llms import create_llm

    return create_llm(llm_name)
