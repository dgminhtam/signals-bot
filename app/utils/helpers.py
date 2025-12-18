import random

CTA_PHRASES = [
    "Cập nhật tin tức thị trường nóng hổi đây ạ...",
    "Điểm tin thị trường mới nhất, mời cả nhà cùng xem...",
    "Tin tức tài chính mới nhất vừa được cập nhật...",
    "Mời anh chị em cùng điểm qua diễn biến thị trường...",
    "Bản tin tài chính cập nhật, đừng bỏ lỡ nhé mọi người..."
]

def get_random_cta() -> str:
    """
    Trả về một câu Call-to-Action ngẫu nhiên.
    """
    return random.choice(CTA_PHRASES)
