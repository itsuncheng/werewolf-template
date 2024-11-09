from typing import Any, Dict
import asyncio
import logging
from collections import defaultdict

from openai import RateLimitError
from sentient_campaign.agents.v1.api import IReactiveAgent
from sentient_campaign.agents.v1.message import (
    ActivityMessage,
    ActivityResponse,
    TextContent,
    MessageChannelType,
)
from tenacity import (
    retry,
    stop_after_attempt,
    retry_if_exception_type,
    wait_exponential,
)

from .game_state import GameState
from .decider_agent import ThinkingAgent
from ..prompts.base_prompts import *
from ..prompts.thinking_prompts import *

logger = logging.getLogger(__name__)

GAME_CHANNEL = "play-arena"
WOLFS_CHANNEL = "wolf's-den"
MODERATOR_NAME = "moderator"

class AutogenCoTAgent(IReactiveAgent):
    def __init__(self):
        self.game_state = GameState()
        self.thinking_agent = None
        logger.debug("AutogenCoTAgent initialized.")

    def __initialize__(self, name: str, description: str, config: dict = None):
        super().__initialize__(name, description, config)
        self._name = name
        self._description = description
        self.config = config

        llm_config = {
            "config_list": [self.sentient_llm_config["config_list"][0]]
        }

        # Initialize the thinking agent with appropriate role prompt once we know the role
        self.thinking_agent = ThinkingAgent(
            name=name,
            role_prompt="Initialized role prompt - will be updated when role is known",
            llm_config=llm_config
        )

    async def async_notify(self, message: ActivityMessage):
        logger.info(f"ASYNC NOTIFY called with message: {message}")
        
        if message.header.channel_type == MessageChannelType.DIRECT:
            self.game_state.add_direct_message(message.header.sender, message.content.text)
            
            if not self.game_state.role and message.header.sender == MODERATOR_NAME:
                self.game_state.role = self._find_my_role(message)
                self._update_thinking_agent_role()
                logger.info(f"Role found for user {self._name}: {self.game_state.role}")
        else:
            self.game_state.add_group_message(
                message.header.channel,
                message.header.sender,
                message.content.text
            )
            
            if (message.header.channel == GAME_CHANNEL and 
                message.header.sender == MODERATOR_NAME and 
                not self.game_state.game_intro):
                self.game_state.game_intro = message.content.text

    @retry(
        wait=wait_exponential(multiplier=1, min=20, max=300),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(RateLimitError),
    )
    def _find_my_role(self, message: ActivityMessage) -> str:
        response = self.thinking_agent.openai_client.chat.completions.create(
            model=self.thinking_agent.model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are helping identify a player's role in a Werewolf game for player {self._name}",
                },
                {
                    "role": "user",
                    "content": f"Based on this moderator message, what is my role? Answer with just the role name (wolf, villager, seer, or doctor): {message.content.text}",
                },
            ],
        )
        role_guess = response.choices[0].message.content.lower()
        
        if "villager" in role_guess:
            return "villager"
        elif "seer" in role_guess:
            return "seer"
        elif "doctor" in role_guess:
            return "doctor"
        else:
            return "wolf"

    def _update_thinking_agent_role(self):
        role_prompts = {
            "wolf": WOLF_SYSTEM_PROMPT,
            "villager": VILLAGER_SYSTEM_PROMPT,
            "seer": SEER_SYSTEM_PROMPT,
            "doctor": DOCTOR_SYSTEM_PROMPT
        }
        self.thinking_agent.system_message = role_prompts[self.game_state.role]

    async def async_respond(self, message: ActivityMessage) -> ActivityResponse:
        logger.info(f"ASYNC RESPOND called with message: {message}")

        if message.header.channel_type == MessageChannelType.DIRECT:
            if message.header.sender == MODERATOR_NAME:
                response_message = await self._handle_moderator_direct_message(message)
        else:
            response_message = await self._handle_group_message(message)

        return ActivityResponse(response=TextContent(text=response_message))

    async def _handle_moderator_direct_message(self, message: ActivityMessage) -> str:
        self.game_state.add_direct_message(message.header.sender, message.content.text)
        
        if self.game_state.role == "seer":
            return self._get_response_for_seer_guess(message)
        elif self.game_state.role == "doctor":
            return self._get_response_for_doctors_save(message)
        
        return "Acknowledged"

    async def _handle_group_message(self, message: ActivityMessage) -> str:
        self.game_state.add_group_message(
            message.header.channel,
            message.header.sender,
            message.content.text
        )

        if message.header.channel == GAME_CHANNEL:
            return self._get_discussion_message_or_vote_response_for_common_room(message)
        elif message.header.channel == WOLFS_CHANNEL:
            return self._get_response_for_wolf_channel_to_kill_villagers(message)
        
        return "Acknowledged"

    # The following methods would be implemented similarly to the original CoT agent
    # but using the thinking_agent for generating responses
    def _get_response_for_seer_guess(self, message: ActivityMessage) -> str:
        seer_checks_info = "\n".join([f"Checked {player}: {result}" for player, result in self.game_state.seer_checks.items()])
        game_situation = f"{self.game_state.get_interwoven_history()}\n\nMy past seer checks:\n{seer_checks_info}"
        
        inner_monologue = self.thinking_agent.get_inner_monologue(
            SEER_SYSTEM_PROMPT,
            game_situation,
            SEER_SPECIFIC_PROMPT
        )

        action = self.thinking_agent.get_final_action(
            SEER_SYSTEM_PROMPT,
            game_situation,
            inner_monologue,
            "choice of player to investigate"
        )
        
        return action

    def _get_response_for_doctors_save(self, message: ActivityMessage) -> str:
        game_situation = self.game_state.get_interwoven_history()
        
        inner_monologue = self.thinking_agent.get_inner_monologue(
            DOCTOR_SYSTEM_PROMPT,
            game_situation,
            DOCTOR_SPECIFIC_PROMPT
        )

        action = self.thinking_agent.get_final_action(
            DOCTOR_SYSTEM_PROMPT,
            game_situation,
            inner_monologue,
            "choice of player to protect"
        )
        
        return action

    def _get_discussion_message_or_vote_response_for_common_room(self, message: ActivityMessage) -> str:
        role_prompt = getattr(self, f"{self.game_state.role.upper()}_PROMPT", VILLAGER_SYSTEM_PROMPT)
        game_situation = self.game_state.get_interwoven_history()
        
        inner_monologue = self.thinking_agent.get_inner_monologue(
            role_prompt,
            game_situation,
            DISCUSSION_SPECIFIC_PROMPT
        )

        # Determine if this is a voting phase by checking the moderator's recent messages
        recent_mod_messages = [msg for sender, msg in self.game_state.group_channel_messages[GAME_CHANNEL][-5:]
                             if sender == MODERATOR_NAME]
        is_voting = any("vote" in msg.lower() for msg in recent_mod_messages)
        
        action_type = "vote for elimination" if is_voting else "response to the discussion"
        action = self.thinking_agent.get_final_action(
            role_prompt,
            game_situation,
            inner_monologue,
            action_type
        )
        
        return action

    def _get_response_for_wolf_channel_to_kill_villagers(self, message: ActivityMessage) -> str:
        if self.game_state.role != "wolf":
            return "I am not a werewolf and cannot participate in this channel."
        
        game_situation = self.game_state.get_interwoven_history(include_wolf_channel=True)
        
        inner_monologue = self.thinking_agent.get_inner_monologue(
            WOLF_SYSTEM_PROMPT,
            game_situation,
            WOLF_SPECIFIC_PROMPT
        )

        action = self.thinking_agent.get_final_action(
            WOLF_SYSTEM_PROMPT,
            game_situation,
            inner_monologue,
            "target for elimination"
        )
        
        return action