from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class AIService(ABC):
    """Abstract Base Class định nghĩa interface cho các AI Service (Async Version)"""

    @abstractmethod
    async def generate_content(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Sinh nội dung từ prompt (Async).
        Args:
            prompt (str): Text Prompt đầu vào.
            schema (Optional[Dict]): JSON Schema để validate output (nếu model support).
        Returns:
            Optional[str]: Text response từ AI.
        """
        pass
