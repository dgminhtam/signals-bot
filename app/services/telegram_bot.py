# telegram_bot.py
import os
import asyncio
from telegram import Bot
from typing import List, Optional
from app.core import config 

# Load biến môi trường từ config
TELEGRAM_TOKEN = config.TELEGRAM_TOKEN
TELEGRAM_CHAT_ID = config.TELEGRAM_CHAT_ID
logger = config.logger

# Global Bot Instance (Lazy load)
_bot_instance = None

def get_bot_instance() -> Optional[Bot]:
    global _bot_instance
    if not TELEGRAM_TOKEN:
        return None
    if _bot_instance is None:
        _bot_instance = Bot(token=TELEGRAM_TOKEN)
    return _bot_instance

async def send_report_to_telegram(report_content: str, image_paths: List[str]) -> None:
    """
    Gửi báo cáo kèm ảnh vào Telegram Group (Async)
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ Chưa cấu hình TELEGRAM_TOKEN hoặc CHAT_ID.")
        return

    logger.info("🚀 Đang gửi báo cáo lên Telegram...")
    
    try:
        bot = get_bot_instance()
        
        # 1. Xử lý ảnh (Chấp nhận cả Local File và URL)
        valid_images = []
        for img in image_paths:
            if img:
                if img.startswith("http"): # URL
                    valid_images.append(img)
                elif os.path.exists(img): # Local file
                    valid_images.append(img)
        
        if not valid_images:
            # Nếu không có ảnh, chỉ gửi text
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=report_content, parse_mode='HTML')
        else:
            # 2. Gửi ảnh đầu tiên kèm caption (text phân tích)
            # Telegram caption max 1024 ký tự
            caption_text = report_content[:1024] if len(report_content) <= 1024 else report_content[:1020] + "..."
            
            first_img = valid_images[0]
            if first_img.startswith("http"):
                 # Gửi URL trực tiếp
                 await bot.send_photo(
                    chat_id=TELEGRAM_CHAT_ID, 
                    photo=first_img,
                    caption=caption_text,
                    parse_mode='HTML'
                )
            else:
                # Gửi Local File
                with open(first_img, 'rb') as photo:
                    await bot.send_photo(
                        chat_id=TELEGRAM_CHAT_ID, 
                        photo=photo,
                        caption=caption_text,
                        parse_mode='HTML'
                    )
            
            # Nếu text quá dài, gửi phần còn lại
            if len(report_content) > 1024:
                remaining_text = report_content[1020:]
                # Chia nhỏ nếu vẫn quá dài (Telegram limit 4096 cho message)
                chunk_size = 4000
                for i in range(0, len(remaining_text), chunk_size):
                    await bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID, 
                        text=remaining_text[i:i+chunk_size], 
                        parse_mode='HTML'
                    )

        logger.info("✅ Đã gửi thành công lên Telegram!")

    except Exception as e:
        logger.error(f"❌ Lỗi gửi Telegram: {e}")

async def send_message_async(content: str) -> None:
    """
    Hàm async đơn giản để gửi text message.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    try:
        bot = get_bot_instance()
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=content, parse_mode='HTML')
    except Exception as e:
        logger.error(f"❌ Lỗi gửi Telegram Message: {e}")
