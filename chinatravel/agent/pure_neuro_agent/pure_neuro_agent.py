import ast

from chinatravel.agent.base import AbstractAgent, AgentReturnInfo
from chinatravel.agent.pure_neuro_agent.prompts import DIRECT_PROMPT


class Notebook:
    def __init__(self):
        self.note = ""

    def write(self, description: str, content: str):
        self.note += description.strip() + "\n"
        self.note += content.strip() + "\n"
        return "NoteBook updated."

    def read(self):
        return self.note

    def reset(self):
        self.note = ""


def _parse_literal_call(action: str, expected_name: str) -> tuple[list, dict]:
    parsed = ast.parse(action, mode="eval").body
    if not isinstance(parsed, ast.Call) or not isinstance(parsed.func, ast.Name):
        raise ValueError(f"Expected {expected_name}(...)")
    if parsed.func.id != expected_name:
        raise ValueError(f"Expected {expected_name}(...), got {parsed.func.id}(...)")
    args = [ast.literal_eval(arg) for arg in parsed.args]
    kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in parsed.keywords if kw.arg}
    return args, kwargs


class ActAgent(AbstractAgent):
    def __init__(
        self,
        env,
        backbone_llm,
        prompt,
        max_steps=50,
        plan_prompt=DIRECT_PROMPT,
        debug=True,
    ):
        super().__init__(env)

        self.backbone_llm = backbone_llm
        self.max_steps = max_steps
        self.debug = debug
        self.prompt = prompt
        self.plan_prompt = plan_prompt

        self.json_scratchpad = []
        self.cur_step = 0
        self.finished = False
        self.notebook = Notebook()

        self.next_page_cnt = 0
        self.notedown_cnt = 0

    def reset(self):
        self._log = []
        self._ans = ""
        self.cur_step = 0
        self.finished = False
        self.json_scratchpad = []
        self.notebook.reset()
        self.next_page_cnt = 0
        self.notedown_cnt = 0
        self.backbone_llm.input_token_count = 0
        self.backbone_llm.output_token_count = 0
        self.backbone_llm.input_token_maxx = 0

    def run(self, query):
        self.reset()
        query = self.prompt + query
        self.json_scratchpad.append({"role": "user", "content": query})
        self._log.append({"Query": query})

        while self.cur_step < self.max_steps and not self.finished:
            self.step()
        if self.finished:
            return AgentReturnInfo(
                ans=self._ans,
                log=self._log,
            )
        else:
            return AgentReturnInfo(
                ans='{"error": "Exceed maximum steps"}',
                log=self._log,
            )

    def step(self):
        self.cur_step += 1
        self.act()

    def act(self):
        # Act
        self.json_scratchpad.append(
            {"role": "user", "content": f"Action[{self.cur_step}]:"}
        )
        action = self.backbone_llm(self.json_scratchpad, one_line=True)
        self.json_scratchpad.append({"role": "assistant", "content": action})
        self._log.append({f"Action[{self.cur_step}]": action})
        if self.debug:
            print(f"Action {self.cur_step}: {action}")

        # Observe
        self.json_scratchpad.append(
            {"role": "user", "content": f"Observation[{self.cur_step}]:"}
        )
        observation = ""
        if action.startswith("Action"):
            action = action.split(":", 1)[1].strip()
        if action.endswith("<STOP>"):
            action = action[: -len("<STOP>")].strip()
        action_cmd = action.split("(")[0].strip()
        if action_cmd == "notedown":
            try:
                args, kwargs = _parse_literal_call(action, "notedown")
                observation = self.notebook.write(*args, **kwargs)
                self.notedown_cnt += 1
                if self.notedown_cnt >= 3:
                    self.notedown_cnt = 1
                    observation = (
                        observation
                        + "\n"
                        + "Please note down everything in one time. Anyway, it is noted down."
                    )
            except Exception as e:
                observation = "Error to note down: " + str(e)
        elif action_cmd == "plan":
            self.finished = True
            try:
                args, kwargs = _parse_literal_call(action, "plan")
                observation = self.plan(*args, **kwargs)
                self._ans = observation
            except Exception as e:
                observation = "Error to plan: " + str(e)
        else:
            observation = str(self.env(action))
            if "next_page" in action:
                self.next_page_cnt += 1
                if self.next_page_cnt >= 3:
                    self.next_page_cnt = 1
                    observation = (
                        "Use next_page() too many times. Please ensure your action is reasonable. Only call next_page() when you didn't get the expected results."
                        + "\n"
                        + observation
                    )
            if observation == "No data." and "select" in action:
                if "cuisine" in action:
                    observation = "Maybe you need use restaurants_cuisine(city) to learn the cuisine."
                elif "attraction" in action and "type" in action:
                    observation = "Maybe you need use attractions_types(city) to learn the attraction type."

        self.json_scratchpad.append({"role": "user", "content": observation})
        self._log.append({f"Observation[{self.cur_step}]": observation})
        if self.debug:
            print(f"Observation {self.cur_step}: {observation}")

    def plan(self, query):
        query = self.plan_prompt + self.notebook.read() + query
        query = [{"role": "user", "content": query}]
        return self.backbone_llm(query, json_mode=True, one_line=False)


class ReActAgent(ActAgent):
    def think(self):
        self.json_scratchpad.append(
            {"role": "user", "content": f"Thought[{self.cur_step}]:"}
        )
        thought = self.backbone_llm(self.json_scratchpad, one_line=True)
        self.json_scratchpad.append({"role": "assistant", "content": thought})
        self._log.append({f"Thought[{self.cur_step}]": thought})
        if self.debug:
            print(f"Thought {self.cur_step}: {thought}")

    def step(self):
        self.cur_step += 1
        self.think()
        self.act()


if __name__ == "__main__":
    import os

    from chinatravel.agent.llms import create_llm
    from chinatravel.environment.world_env import WorldEnv
    from chinatravel.agent.pure_neuro_agent.prompts import (
        ONESHOT_REACT_INSTRUCTION,
    )

    print(os.environ.get("OPENAI_API_KEY"))

    llm = create_llm(None)
    env = WorldEnv()
    agent = ReActAgent(env, llm, ONESHOT_REACT_INSTRUCTION, debug=True)
    query = "当前位置上海。我一个人想去杭州玩1天，预算3000人民币，请给我一个旅行规划。"
    results = agent(query)
