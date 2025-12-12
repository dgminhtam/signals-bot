import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

# Lấy API keys (hỗ trợ cả single key và multi-key)
keys_str = os.getenv("GEMINI_API_KEY", "")
api_keys = [k.strip() for k in keys_str.split(',') if k.strip()]

if not api_keys:
    print("❌ Không tìm thấy GEMINI_API_KEY trong file .env")
    print("Hãy mở file .env và kiểm tra lại!")
    exit(1)

# Thử key đầu tiên
print(f"🔑 Đang test với API Key: ...{api_keys[0][-8:]}")
genai.configure(api_key=api_keys[0])

print("\nDANH SÁCH MODEL KHẢ DỤNG:")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ {m.name}")
except Exception as e:
    print(f"\n❌ Lỗi khi test API Key: {e}")
    print("\n💡 Hướng dẫn khắc phục:")
    print("1. Kiểm tra file .env có chứa GEMINI_API_KEY chính xác không")
    print("2. Lấy key mới tại: https://aistudio.google.com/apikey")
    print("3. Format trong .env: GEMINI_API_KEY=AIzaSy...")