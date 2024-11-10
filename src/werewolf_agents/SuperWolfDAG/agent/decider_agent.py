from autogen import ConversableAgent
import logging
from typing import Any, Dict
from openai import OpenAI

from werewolf_agents.cot_sample.prompts.final_action_prompts import get_initial_action_prompt, get_reflection_prompt

logger = logging.getLogger(__name__)

class DeciderAgent(ConversableAgent):
    def __init__(self, name: str, role_prompt: str, llm_config: Dict[str, Any]):
        super().__init__(
            name=name,
            system_message=role_prompt,
            llm_config=llm_config
        )
        
        self.openai_client = OpenAI(
            api_key=llm_config["config_list"][0]["api_key"],
            base_url=llm_config["config_list"][0]["base_url"],
        )
        self.model = llm_config["config_list"][0]["model"]

    def get_inner_monologue(self, role_prompt: str, game_situation: str, specific_prompt: str) -> str:
        prompt = f"""{role_prompt}

Current game situation (including your past thoughts and actions): 
{game_situation}

{specific_prompt}"""

        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": f"You are a {self.name} in a Werewolf game."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content

    def get_final_action(self, role_prompt: str, game_situation: str, inner_monologue: str, action_type: str) -> str:
        # Initial action prompt
        prompt = get_initial_action_prompt(role_prompt, game_situation, inner_monologue, action_type)
        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": f"You are a {self.name} in a Werewolf game."},
                {"role": "user", "content": prompt}
            ]
        )
        initial_action = response.choices[0].message.content

        # Reflection prompt
        reflection_prompt = get_reflection_prompt(role_prompt, game_situation, inner_monologue, initial_action)

        reflection_response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": f"You are a {self.name} in a Werewolf game."},
                {"role": "user", "content": reflection_prompt}
            ]
        )
        reflection = reflection_response.choices[0].message.content

        # Final action prompt
        final_prompt = f"""{role_prompt}

Current game situation (including past thoughts and actions):
{game_situation}

Your thoughts:
{inner_monologue}

Your initial action:
{initial_action}

Your reflection:
{reflection}

Based on your thoughts, the current situation, and your reflection, what is your absolute final {action_type}? Provide only the final action, ensuring it includes a specific player name if voting or targeting is involved."""

        final_response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": f"You are a {self.name} in a Werewolf game."},
                {"role": "user", "content": final_prompt}
            ]
        )
        
        return final_response.choices[0].message.content.strip()