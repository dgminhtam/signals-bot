from app.services.wordpress_service import wordpress_service
import sys
import io

# Set encoding to utf-8 for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("--- WORDPRESS HEADER FIX VERIFICATION ---")

def check_conversion(input_text, expected_fragment, description):
    html = wordpress_service.convert_telegram_to_html(input_text)
    print(f"TEST: {description}")
    print(f"INPUT: '{input_text}'")
    print(f"OUTPUT: '{html}'")
    
    if expected_fragment in html:
        print("✅ PASSED")
    else:
        print(f"❌ FAILED. Expected to find: '{expected_fragment}'")
    
    if "<h1>" in html:
        print("❌ FAILED. Found <h1> tag (Header collision detected).")
    else:
        print("✅ PASSED. No <h1> tag found.")
    print("-" * 20)

# Test 1: Start of line hashtag (The main issue)
check_conversion("#Hashtag", '<span class="hashtag">#Hashtag</span>', "Start of line hashtag")

# Test 2: Inline hashtag
check_conversion("Text #Inline", '<span class="hashtag">#Inline</span>', "Middline hashtag")

# Test 3: URL (Should NOT be wrapped)
check_conversion("http://example.com/#anchor", "http://example.com/#anchor", "URL anchor")
