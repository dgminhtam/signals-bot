import random

CTA_PHRASES = [
    "Đọc tin hôm nay thôi mọi người ơi...",
    "Cập nhật tin tức thị trường nóng hổi đây ạ...",
    "Điểm tin thị trường mới nhất, mời cả nhà cùng xem...",
    "Tin tức tài chính đáng chú ý vừa được cập nhật...",
    "Mời anh chị em cùng điểm qua diễn biến thị trường...",
    "Cùng xem tin tức gì đang tác động đến giá vàng nhé...",
    "Bản tin tài chính cập nhật, đừng bỏ lỡ nhé mọi người...",
    "Tin nóng vừa về, mời mọi người tham khảo...",
]

def get_random_cta() -> str:
    """
    Trả về một câu Call-to-Action ngẫu nhiên.
    """
    return random.choice(CTA_PHRASES)
