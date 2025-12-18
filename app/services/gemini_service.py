import google.generativeai as genai
from typing import List, Dict, Any, Optional
from app.core import config
from app.services.ai_base import AIService
import logging
import asyncio
import time

logger = config.logger

class KeyManager:
    def __init__(self, keys: List[str]):
        self.keys = keys
        self.current_index = 0
        logger.info(f"🔑 Loaded {len(keys)} Gemini API Keys for rotation.")
    
    def get_current_key(self) -> str:
        if not self.keys:
            raise ValueError("No Gemini API keys available")
        return self.keys[self.current_index]
    
    def switch_key(self) -> str:
        """Chuyển sang key tiếp theo (Circular)"""
        if len(self.keys) <= 1:
            logger.warning("⚠️ Only 1 key available, cannot rotate.")
            return self.get_current_key()
        
        self.current_index = (self.current_index + 1) % len(self.keys)
        new_key = self.get_current_key()
        logger.info(f"🔄 Switching Gemini API Key -> ...{new_key[-8:]}")
        return new_key

class GeminiService(AIService):
    def __init__(self):
        self.key_manager = KeyManager(config.GEMINI_API_KEYS)
        self._configure_genai()
        self.generation_config = {
            "temperature": 0.4,
            "response_mime_type": "application/json"
        }

    def _configure_genai(self, key: Optional[str] = None):
        if not key:
            key = self.key_manager.get_current_key()
        genai.configure(api_key=key)

    def _get_model(self, schema: Optional[Dict[str, Any]] = None):
        """Helper để lấy model từ config với Schema cụ thể"""
        config_copy = self.generation_config.copy()
        if schema:
            config_copy["response_schema"] = schema
        
        try:
            return genai.GenerativeModel(config.GEMINI_MODEL_NAME, generation_config=config_copy)
        except Exception as e:
            logger.warning(f"⚠️ Fallback to {config.GEMINI_FALLBACK_MODEL} due to: {e}")
            return genai.GenerativeModel(config.GEMINI_FALLBACK_MODEL, generation_config=config_copy)

    async def generate_content(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Triển khai generate_content cho Gemini với Retry & Key Rotation (Async)
        """
        retries = 10
        attempt = 0
        
        while attempt < retries:
            try:
                model = self._get_model(schema)
                # Sử dụng generate_content_async của Google SDK
                response = await model.generate_content_async(prompt)
                return response.text
            except Exception as e:
                error_msg = str(e).lower()
                # Check lỗi Quota (429) hoặc lỗi Model quá tải
                if "429" in error_msg or "quota" in error_msg or "overloaded" in error_msg:
                    logger.warning(f"⚠️ Gemini Quota Exceeded / Error: {e}")
                    
                    # Rotate Key
                    new_key = self.key_manager.switch_key()
                    self._configure_genai(new_key)
                    
                    # Exponential Backoff with Async Sleep
                    backoff_time = min(2 ** attempt, 60)
                    logger.info(f"🔄 Retry #{attempt + 1} - Chờ {backoff_time}s (Exponential Backoff)...")
                    await asyncio.sleep(backoff_time)
                else:
                    logger.error(f"❌ Unrecoverable Gemini Error: {e}")
                    return None
                
                attempt += 1
                
        logger.error("❌ Gemini Hết lượt thử (Retries Exhausted).")
        return None
