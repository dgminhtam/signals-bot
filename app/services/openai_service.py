from openai import OpenAI
from typing import Dict, Any, Optional
from app.core import config
from app.services.ai_base import AIService
import logging
import json

logger = config.logger

class OpenAIService(AIService):
    def __init__(self):
        if not config.OPENAI_API_KEY:
            raise ValueError("❌ Missing OPENAI_API_KEY in config for OpenAI Provider")
            
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.OPENAI_MODEL_NAME

    def generate_content(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Triển khai generate_content cho OpenAI (ChatGPT)
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

            # Nếu có schema, dùng tính năng Response Format (JSON Mode)
            # Lưu ý: OpenAI yêu cầu từ khóa 'json' trong prompt khi dùng json_object
            if schema:
                params["response_format"] = {"type": "json_object"}
                # Ensure the prompt instructs JSON output (usually already in prompt templates)
            
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"❌ OpenAI Error: {e}")
            return None
