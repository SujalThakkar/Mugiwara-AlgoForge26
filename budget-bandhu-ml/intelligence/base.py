"""
Base interfaces that both of you will respect.
This is your contract—don't break it.
"""
from abc import ABC, abstractmethod
from typing import Dict, List

class IntelligenceComponent(ABC):
    """All ML components inherit this"""
    
    @abstractmethod
    def process(self, input_data: Dict) -> Dict:
        """
        Standard interface for all intelligence components.
        Input: arbitrary dict
        Output: standardized dict
        """
        pass

class MemoryProvider(ABC):
    """Memory interface for Agent Controller"""
    
    @abstractmethod
    def retrieve_context(self, user_id: int, query: str) -> Dict:
        pass
    
    @abstractmethod
    def store_episodic(self, user_id: int, memory: Dict) -> int:
        pass
    
    @abstractmethod
    def store_semantic(self, user_id: int, memory: Dict) -> int:
        pass
