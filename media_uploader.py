import os
import re
import time
import json
import base64
import requests
import csv
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

WP_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_IMAGE_MODEL = os.getenv("GOOGLE_IMAGE_MODEL", "gemini-2.0-flash-exp-image-generation")

# Rate limit — 2 images per minute, 32 second sleep to be safe
IMAGE_SLEEP = 32

# WordPress auth
credentials = f"{WP_USERNAME}:{WP_APP_PASSWORD}"
token = base64.b64encode(credentials.encode()).decode()
AUTH_HEADERS = {"Authorization": f"Basic {token}"}

def slugify(title):
    return title.lower().replace(" ", "-").replace("/", "-").replace(":", "").replace("?", "").replace("!", "").replace(",", "").replace("'", "").replace("\"", "")

def load_csv(filename):
    rows = []
    with open(filename, "r") as f:
        reader = csv.DictReader(f, delimiter="|")
        for row in reader:
            cleaned = {k.strip(): v.strip() for k, v in row.items() if k}
            rows.append(cleaned)
    return rows

def load_all_rows():
    all_rows = []
    silos = [f for f in os.listdir("silos") if f.endswith(".csv")]
    for silo in silos:
        rows = load_csv(os.path.join("silos", silo))
        all_rows.extend(rows)
    return all_rows

def find_row_for_draft(draft_filename):
    basename = os.path.basename(draft_filename)
    slug = basename.replace(".md", "")
    all_rows = load_all_rows()
    for row in all_rows:
        title = row.get("Title", "")
        if slugify(title) == slug:
            return row
    return None

def generate_image(prompt):
    """Generate image using Google AI Studio and return raw bytes"""
    print(f"    🎨 Generating: {prompt[:60]}...")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GOOGLE_IMAGE_MODEL}:generateContent?key={GOOGLE_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
    }

    try:
        response = requests.post(url, json=payload, timeout=60)

        if response.status_code == 200:
            data = response.json()
            for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "inlineData" in part:
                    image_data = part["inlineData"]["data"]
                    return base64.b64decode(image_data)
            print("    ⚠️  No image data in response")
            return None
        else:
            print(f"    ❌ Generation failed: {response.status_code} - {response.text[:200]}")
            return None

    except Exception as e:
        print(f"    ❌ Generation error: {e}")
        return None

def convert_to_avif(image_bytes):
    """Convert image bytes to AVIF format"""
    try:
        from PIL import Image
        try:
            import pillow_avif
        except ImportError:
            pass

        img = Image.open(BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        output = BytesIO()
        img.save(output, format="AVIF", quality=80)
        output.seek(0)
        print(f"    ✅ Converted to AVIF")
        return output.read(), True

    except Exception as e:
        print(f"    ⚠️  AVIF conversion failed: {e} — using original")
        return image_bytes, False

def upload_to_wordpress(image_bytes, filename, title, alt_text, caption, description, is_avif=True):
    """Upload image to WordPress media library and fill all fields"""
    try:
        content_type = "image/avif" if is_avif else "image/jpeg"
        ext = ".avif" if is_avif else ".jpg"
        clean_filename = filename + ext

        headers = {
            **AUTH_HEADERS,
            "Content-Disposition": f'attachment; filename="{clean_filename}"',
            "Content-Type": content_type
        }

        print(f"    📤 Uploading to WordPress...")
        response = requests.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            headers=headers,
            data=image_bytes
        )

        if response.status_code == 201:
            media = response.json()
            media_id = media["id"]
            media_url = media["source_url"]

            # Fill in all media fields
            requests.post(
                f"{WP_URL}/wp-json/wp/v2/media/{media_id}",
                headers={**AUTH_HEADERS, "Content-Type": "application/json"},
                json={
                    "title": title,
                    "alt_text": alt_text,
                    "caption": caption,
                    "description": description
                }
            )

            print(f"    ✅ Uploaded! ID: {media_id}")
            return media_id, media_url
        else:
            print(f"    ❌ Upload failed: {response.status_code} - {response.text[:200]}")
            return None, None

    except Exception as e:
        print(f"    ❌ Upload error: {e}")
        return None, None

def get_inline_image_count(article_size):
    size = article_size.lower()
    if "x-small" in size:
        return 1
    elif "small" in size:
        return 2
    elif "medium" in size:
        return 3
    elif "large" in size:
        return 4
    elif "pillar" in size:
        return 4
    return 2

def get_h2_sections(lines):
    skip = ["faq", "key takeaways", "conclusion", "frequently asked"]
    sections = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            if not any(s in heading for s in skip):
                sections.append((i, line[3:].strip()))
    return sections

def process_article(draft_file):
    print(f"\n🖼️  Processing: {os.path.basename(draft_file)}\n")
    print("-" * 50)

    # Find matching PSV row
    row = find_row_for_draft(draft_file)
    if not row:
        print("  ❌ Could not find matching PSV row.")
        return

    title = row.get("Title", "")
    article_size = row.get("Article Size", "")
    inline_count = get_inline_image_count(article_size)
    slug = slugify(title)

    print(f"  Title:         {title}")
    print(f"  Inline Images: {inline_count}")
    print()

    # Read markdown
    with open(draft_file, "r") as f:
        content = f.read()

    lines = content.split("\n")

    # Find eligible H2 sections
    sections = get_h2_sections(lines)

    if not sections:
        print("  ⚠️  No eligible H2 sections found.")
        return

    # Pick evenly spaced injection points
    if inline_count >= len(sections):
        selected = sections
    else:
        step = len(sections) / inline_count
        selected = [sections[int(i * step)] for i in range(inline_count)]

    # Generate, convert, upload inline images
    image_insertions = []
    for i, (line_index, heading) in enumerate(selected, 1):
        print(f"  Inline Image {i}/{len(selected)}: {heading[:50]}")

        prompt = f"{title} {heading} professional photography high quality"
        image_bytes = generate_image(prompt)

        if not image_bytes:
            print(f"    ⚠️  Skipping image {i}")
            if i < len(selected):
                print(f"    ⏳ Waiting {IMAGE_SLEEP} seconds...")
                time.sleep(IMAGE_SLEEP)
            continue

        avif_bytes, is_avif = convert_to_avif(image_bytes)
        img_filename = f"{slug}-image-{i}"
        alt_text = f"{title} - {heading}"

        media_id, media_url = upload_to_wordpress(
            avif_bytes,
            img_filename,
            title=f"{title} - {heading}",
            alt_text=alt_text,
            caption=alt_text,
            description=alt_text,
            is_avif=is_avif
        )

        if media_url:
            img_tag = f"\n![{alt_text}]({media_url})\n"
            image_insertions.append((line_index, img_tag))
            print(f"    ✅ Ready to inject\n")

        if i < len(selected):
            print(f"    ⏳ Waiting {IMAGE_SLEEP} seconds...")
            time.sleep(IMAGE_SLEEP)

    # Inject images into markdown in reverse order
    for line_index, img_tag in sorted(image_insertions, reverse=True):
        lines.insert(line_index + 1, img_tag)

    content = "\n".join(lines)

    # Generate featured image — no dependency on any file
    print(f"  🌟 Generating featured image...")
    print(f"    ⏳ Waiting {IMAGE_SLEEP} seconds...")
    time.sleep(IMAGE_SLEEP)

    featured_prompt = f"{title} hero image professional digital art cinematic"
    image_bytes = generate_image(featured_prompt)

    featured_media_id = None
    if image_bytes:
        avif_bytes, is_avif = convert_to_avif(image_bytes)

        featured_media_id, featured_media_url = upload_to_wordpress(
            avif_bytes,
            f"{slug}-featured",
            title=f"{title} - Featured Image",
            alt_text=f"{title} featured image",
            caption=title,
            description=f"Featured image for {title}",
            is_avif=is_avif
        )

        if featured_media_id:
            # Save featured media ID for wp_publisher to use
            mediaid_file = os.path.join("drafts", slug + "-mediaid.txt")
            with open(mediaid_file, "w") as f:
                f.write(str(featured_media_id))
            print(f"    ✅ Featured media ID saved: {featured_media_id}")

    # Save updated markdown
    with open(draft_file, "w") as f:
        f.write(content)

    print(f"\n  💾 Article saved with WordPress media URLs")
    print(f"  ✅ Done: {title[:60]}\n")

def select_draft():
    drafts = [f for f in os.listdir("drafts") if f.endswith(".md")]
    if not drafts:
        print("\n❌ No drafts found in drafts/ folder.")
        return None
    print("\n📋 Available drafts:")
    for i, f in enumerate(drafts, 1):
        display = f.replace(".md", "").replace("-", " ").title()
        print(f"  {i}. {display}")
    choice = input("\nSelect draft number: ").strip()
    try:
        return os.path.join("drafts", drafts[int(choice) - 1])
    except:
        print("❌ Invalid selection.")
        return None

def main():
    while True:
        print("\n" + "=" * 50)
        print("      SiloGenius Media Uploader")
        print("=" * 50)
        print("  1. Process one article")
        print("  2. Process all articles")
        print("  3. Exit")
        print("=" * 50)

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            draft = select_draft()
            if draft:
                process_article(draft)

        elif choice == "2":
            drafts = [f for f in os.listdir("drafts") if f.endswith(".md")]
            if drafts:
                print(f"\n🚀 Processing {len(drafts)} articles...\n")
                for i, f in enumerate(drafts, 1):
                    print(f"[{i}/{len(drafts)}]")
                    process_article(os.path.join("drafts", f))
                print("\n✅ All articles processed!\n")
            else:
                print("\n❌ No drafts found.")

        elif choice == "3":
            print("\n👋 Goodbye!\n")
            break

        else:
            print("\n❌ Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
