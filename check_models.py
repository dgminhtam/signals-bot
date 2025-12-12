"""
Script kiểm tra kết nối và danh sách models khả dụng cho tất cả AI providers.
Hỗ trợ: Gemini, OpenAI, Groq
"""
import os
from dotenv import load_dotenv

load_dotenv()

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()

print(f"🤖 AI Provider hiện tại: {AI_PROVIDER.upper()}\n")

# ===== GEMINI =====
if AI_PROVIDER == "gemini":
    import google.generativeai as genai
    
    keys_str = os.getenv("GEMINI_API_KEY", "")
    api_keys = [k.strip() for k in keys_str.split(',') if k.strip()]
    
    if not api_keys:
        print("❌ Không tìm thấy GEMINI_API_KEY trong file .env")
        exit(1)
    
    print(f"🔑 Đang test với API Key: ...{api_keys[0][-8:]}\n")
    genai.configure(api_key=api_keys[0])
    
    print("DANH SÁCH MODEL KHẢ DỤNG:")
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

# ===== OPENAI =====
elif AI_PROVIDER == "openai":
    from openai import OpenAI
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ Không tìm thấy OPENAI_API_KEY trong file .env")
        exit(1)
    
    print(f"🔑 Đang test với API Key: ...{api_key[-8:]}\n")
    client = OpenAI(api_key=api_key)
    
    print("DANH SÁCH MODEL KHẢ DỤNG:")
    try:
        models = client.models.list()
        for m in models.data:
            if 'gpt' in m.id:  # Chỉ hiển thị GPT models
                print(f"✅ {m.id}")
    except Exception as e:
        print(f"\n❌ Lỗi khi test API Key: {e}")
        print("\n💡 Hướng dẫn khắc phục:")
        print("1. Kiểm tra file .env có chứa OPENAI_API_KEY chính xác không")
        print("2. Lấy key mới tại: https://platform.openai.com/api-keys")
        print("3. Format trong .env: OPENAI_API_KEY=sk-proj-...")

# ===== GROQ =====
elif AI_PROVIDER == "groq":
    from groq import Groq
    
    api_key = os.getenv("GROQ_API_KEY")
    
    if not api_key:
        print("❌ Không tìm thấy GROQ_API_KEY trong file .env")
        exit(1)
    
    print(f"🔑 Đang test với API Key: ...{api_key[-8:]}\n")
    client = Groq(api_key=api_key)
    
    print("DANH SÁCH MODEL KHẢ DỤNG:")
    try:
        models = client.models.list()
        for m in models.data:
            print(f"✅ {m.id}")
    except Exception as e:
        print(f"\n❌ Lỗi khi test API Key: {e}")
        print("\n💡 Hướng dẫn khắc phục:")
        print("1. Kiểm tra file .env có chứa GROQ_API_KEY chính xác không")
        print("2. Lấy key mới tại: https://console.groq.com/keys")
        print("3. Format trong .env: GROQ_API_KEY=gsk_...")

else:
    print(f"❌ Provider '{AI_PROVIDER}' không được hỗ trợ!")
    print("Các provider khả dụng: gemini, openai, groq")
    exit(1)