from groq import Groq
from typing import Dict, Any, Optional, List
from app.core import config
from app.services.ai_base import AIService
import logging
import time

logger = config.logger

class KeyManager:
    """Quản lý multiple Groq API Keys cho rotation"""
    def __init__(self, keys: List[str]):
        self.keys = keys
        self.current_index = 0
        logger.info(f"🔑 Loaded {len(keys)} Groq API Keys for rotation.")
    
    def get_current_key(self) -> str:
        if not self.keys:
            raise ValueError("No Groq API keys available")
        return self.keys[self.current_index]
    
    def switch_key(self) -> str:
        """Chuyển sang key tiếp theo (Circular)"""
        if len(self.keys) <= 1:
            logger.warning("⚠️ Only 1 Groq key available, cannot rotate.")
            return self.get_current_key()
        
        self.current_index = (self.current_index + 1) % len(self.keys)
        new_key = self.get_current_key()
        logger.info(f"🔄 Switching Groq API Key -> ...{new_key[-8:]}")
        return new_key

class GroqService(AIService):
    def __init__(self):
        # Hỗ trợ multi-key (comma-separated)
        groq_key_str = config.GROQ_API_KEY or ""
        api_keys = [k.strip() for k in groq_key_str.split(',') if k.strip()]
        
        if not api_keys:
            raise ValueError("❌ Missing GROQ_API_KEY in config for Groq Provider")
        
        self.key_manager = KeyManager(api_keys)
        self.model = config.GROQ_MODEL_NAME
        self._init_client()
    
    def _init_client(self, key: Optional[str] = None):
        """Khởi tạo/Cấu hình lại Groq client với key mới"""
        if not key:
            key = self.key_manager.get_current_key()
        self.client = Groq(api_key=key)

    def generate_content(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Triển khai generate_content cho Groq với Retry & Key Rotation
        """
        retries = 5
        attempt = 0
        
        while attempt < retries:
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
                
                response = self.client.chat.completions.create(**params)
                return response.choices[0].message.content
                
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check lỗi Rate Limit (429) hoặc Quota
                if "429" in error_msg or "rate" in error_msg or "quota" in error_msg or "limit" in error_msg:
                    logger.warning(f"⚠️ Groq Rate Limit / Quota Error: {e}")
                    
                    # Rotate Key nếu có nhiều keys
                    new_key = self.key_manager.switch_key()
                    self._init_client(new_key)
                    
                    # Exponential Backoff (Groq rất nhanh nên backoff ngắn hơn)
                    backoff_time = min(2 ** attempt, 20)  # Max 20s cho Groq
                    logger.info(f"🔄 Retry #{attempt + 1} - Chờ {backoff_time}s (Exponential Backoff)...")
                    time.sleep(backoff_time)
                else:
                    logger.error(f"❌ Unrecoverable Groq Error: {e}")
                    return None
                
                attempt += 1
                
        logger.error("❌ Groq Hết lượt thử (Retries Exhausted).")
        return None
