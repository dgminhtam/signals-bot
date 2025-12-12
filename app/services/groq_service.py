from groq import Groq
from typing import Dict, Any, Optional
from app.core import config
from app.services.ai_base import AIService
import logging
import json

logger = config.logger

class GroqService(AIService):
    def __init__(self):
        if not config.GROQ_API_KEY:
            raise ValueError("❌ Missing GROQ_API_KEY in config for Groq Provider")
            
        self.client = Groq(api_key=config.GROQ_API_KEY)
        self.model = config.GROQ_MODEL_NAME

    def generate_content(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Triển khai generate_content cho Groq Cloud (Llama 3, Mixtral...)
        """
        try:
            # Chuẩn bị params
            params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful financial analyst assistant."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.4,
            }

            # Groq hỗ trợ JSON Mode
            if schema:
                params["response_format"] = {"type": "json_object"}
                # Lưu ý: Prompt cần có từ khóa "json" để kích hoạt JSON Mode trên Groq/Llama
            
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"❌ Groq Error: {e}")
            return None
