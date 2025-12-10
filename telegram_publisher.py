# telegram_publisher.py
import os
import asyncio
from telegram import Bot, InputMediaPhoto
from typing import List, Optional
import config # Import config

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
            # 2. Tạo Album ảnh
            # Gửi Album ảnh trước
            for img_path in valid_images:
                # Mở file để gửi
                media_group.append(InputMediaPhoto(media=open(img_path, 'rb')))

            await bot.send_media_group(chat_id=TELEGRAM_CHAT_ID, media=media_group)

            # 3. Gửi nội dung bài báo cáo ngay sau đó
            # Cắt ngắn nếu quá dài (Telegram max 4096 ký tự cho message)
            final_content = report_content[:4000] 
            
            # Gửi Text với Parse Mode là HTML (để hiển thị Bold, Italic...)
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=final_content, parse_mode='HTML')

        logger.info("✅ Đã gửi thành công lên Telegram!")

    except Exception as e:
        logger.error(f"❌ Lỗi gửi Telegram: {e}")

# Hàm wrapper để gọi từ code đồng bộ (sync) bên ngoài
def run_sending(content: str, images: List[str]) -> None:
    try:
        asyncio.run(send_report_to_telegram(content, images))
    except Exception as e:
        logger.error(f"Lỗi khởi chạy Asyncio: {e}")