"""
Script verified cURL test
"""
from app.services.wordpress_service import wordpress_service
from app.core import config
from datetime import datetime
import os

print(f"Testing with Liveblog ID: {config.WORDPRESS_LIVEBLOG_ID}")

# 1. Test Upload
test_image = "images/chart_price.png"
image_url = None
if os.path.exists(test_image):
    media_id = wordpress_service.upload_image(test_image, f"Test Chart {datetime.now().strftime('%H%M')}")
    if media_id:
        image_url = f"{wordpress_service.url}/wp-content/uploads/{datetime.now().strftime('%Y/%m')}/{os.path.basename(test_image)}"
        print(f"✅ Image URL: {image_url}")

# 2. Test Create Entry
print("Creating Entry...")
entry = wordpress_service.create_liveblog_entry(
    title=f"Update Test {datetime.now().strftime('%H:%M:%S')}",
    content=f"✅ Test từ Python Script.\nẢnh: {image_url}",
    image_url=image_url
)

if entry:
    print(f"✅ SUCCESS! Entry ID: {entry.get('id')}")
    print(f"Link: {entry.get('link')}")
else:
    print("❌ FAILED")
