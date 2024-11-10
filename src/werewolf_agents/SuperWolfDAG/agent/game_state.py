from collections import defaultdict
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

class GameState:
    def __init__(self):
        # self.direct_messages: Dict[str, List[str]] = defaultdict(list)
        # self.group_channel_messages: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        self.game_history: List[str] = []
        # self.seer_checks: Dict[str, str] = {}
        # self.game_intro: str = None
        self.role: str = None

    def add_direct_message(self, sender: str, message: str):
        self.direct_messages[sender].append(message)
        self.game_history.append(f"[From - {sender}| Direct Message]: {message}")

    def add_group_message(self, channel: str, sender: str, message: str):
        self.group_channel_messages[channel].append((sender, message))
        self.game_history.append(f"[From - {sender}| Group Message in {channel}]: {message}")

    def get_interwoven_history(self, include_wolf_channel: bool = False) -> str:
        return "\n".join([
            event for event in self.game_history
            if include_wolf_channel or "wolf's-den" not in event.lower()
        ]) 