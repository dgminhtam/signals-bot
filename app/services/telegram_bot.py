# telegram_bot.py
import os
import asyncio
from telegram import Bot, InputMediaPhoto
from typing import List, Optional
from app.core import config # Updated import

# Load biến môi trường từ config
TELEGRAM_TOKEN = config.TELEGRAM_TOKEN
TELEGRAM_CHAT_ID = config.TELEGRAM_CHAT_ID
logger = config.logger

async def send_report_to_telegram(report_content: str, image_paths: List[str]) -> None:
    """
    Gửi báo cáo kèm ảnh vào Telegram Group (Async)
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ Chưa cấu hình TELEGRAM_TOKEN hoặc CHAT_ID.")
        return

    logger.info("🚀 Đang gửi báo cáo lên Telegram...")
    
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        media_group = []
        
        # 1. Xử lý ảnh (Chỉ lấy ảnh tồn tại)
        valid_images = [img for img in image_paths if img and os.path.exists(img)]
        
        if not valid_images:
            # Nếu không có ảnh, chỉ gửi text
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=report_content, parse_mode='HTML')
        else:
            # 2. Gửi ảnh đầu tiên kèm caption (text phân tích)
            # Telegram caption max 1024 ký tự, nếu dài hơn sẽ gửi riêng
            caption_text = report_content[:1024] if len(report_content) <= 1024 else report_content[:1020] + "..."
            
            with open(valid_images[0], 'rb') as photo:
                await bot.send_photo(
                    chat_id=TELEGRAM_CHAT_ID, 
                    photo=photo,
                    caption=caption_text,
                    parse_mode='HTML'
                )
            
            # Nếu text quá dài, gửi phần còn lại
            if len(report_content) > 1024:
                remaining_text = report_content[1020:]
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=remaining_text, parse_mode='HTML')

        logger.info("✅ Đã gửi thành công lên Telegram!")

    except Exception as e:
        logger.error(f"❌ Lỗi gửi Telegram: {e}")

# Hàm wrapper để gọi từ code đồng bộ (sync) bên ngoài
def run_sending(content: str, images: List[str]) -> None:
    try:
        asyncio.run(send_report_to_telegram(content, images))
    except Exception as e:
        logger.error(f"Lỗi khởi chạy Asyncio: {e}")

def send_message(content: str) -> None:
    """Simple wrapper for sending text only"""
    run_sending(content, [])
