import markdown
import re

def test_markdown(text):
    print(f"RAW INPUT: '{text}'")
    
    # Strategy B: Wrap before markdown
    # Match # followed by word chars, NOT following a word char
    pre_processed = re.sub(r'(?<!\w)(#\w+)', r'<span class="hashtag">\1</span>', text)
    print(f"PRE-PROCESSED: '{pre_processed}'")
    
    html = markdown.markdown(pre_processed)
    print(f"FINAL HTML: '{html}'")
    print("-" * 20)

print("--- DEBUG PRE-PROCESSING ---")
test_markdown("#Hashtag")
test_markdown("#Hashtag #Gold")
test_markdown("# Header Space") # Should match #Header if \w+ matches Header? No, space breaks \w+
# Wait, my regex is #\w+
# # Header -> # matches, then space doesn't match \w. So regex fails. Good.
# But #Header matches? Yes.
# Does python-markdown treat #Header as header?
test_markdown("#Header") 
