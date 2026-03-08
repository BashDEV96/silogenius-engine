import os
import json
import base64
import requests
import csv
from dotenv import load_dotenv
import markdown

# Load environment variables
load_dotenv()

WP_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

# Basic auth header
credentials = f"{WP_USERNAME}:{WP_APP_PASSWORD}"
token = base64.b64encode(credentials.encode()).decode()
HEADERS = {
    "Authorization": f"Basic {token}",
    "Content-Type": "application/json"
}

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

def slugify(title):
    return title.lower().replace(" ", "-").replace("/", "-").replace(":", "").replace("?", "").replace("!", "").replace(",", "").replace("'", "").replace("\"", "")

def find_row_for_draft(draft_filename):
    basename = os.path.basename(draft_filename)
    slug = basename.replace(".md", "")
    all_rows = load_all_rows()
    for row in all_rows:
        title = row.get("Title", "")
        if slugify(title) == slug:
            return row
    return None

def get_or_create_category(category_string):
    parts = [p.strip() for p in category_string.split(">")]
    parent_id = 0
    category_id = 0

    for part in parts:
        response = requests.get(
            f"{WP_URL}/wp-json/wp/v2/categories",
            headers=HEADERS,
            params={"search": part, "parent": parent_id}
        )
        categories = response.json()
        existing = [c for c in categories if c["name"].lower() == part.lower()]

        if existing:
            category_id = existing[0]["id"]
            parent_id = category_id
        else:
            response = requests.post(
                f"{WP_URL}/wp-json/wp/v2/categories",
                headers=HEADERS,
                json={"name": part, "parent": parent_id}
            )
            if response.status_code == 201:
                category_id = response.json()["id"]
                parent_id = category_id
            else:
                print(f"⚠️  Could not create category: {part}")

    return category_id

def get_or_create_tags(tags_string):
    tag_ids = []
    tags = [t.strip() for t in tags_string.split(",")]

    for tag in tags:
        response = requests.get(
            f"{WP_URL}/wp-json/wp/v2/tags",
            headers=HEADERS,
            params={"search": tag}
        )
        existing_tags = response.json()
        existing = [t for t in existing_tags if t["name"].lower() == tag.lower()]

        if existing:
            tag_ids.append(existing[0]["id"])
        else:
            response = requests.post(
                f"{WP_URL}/wp-json/wp/v2/tags",
                headers=HEADERS,
                json={"name": tag}
            )
            if response.status_code == 201:
                tag_ids.append(response.json()["id"])
            else:
                print(f"⚠️  Could not create tag: {tag}")

    return tag_ids

def publish_article(draft_file, status="draft"):
    print(f"\n📤 Publishing: {os.path.basename(draft_file)}\n")
    print("-" * 50)

    # Find matching PSV row
    row = find_row_for_draft(draft_file)
    if not row:
        print("❌ Could not find matching PSV row.")
        return False

    # Read markdown and convert to HTML
    with open(draft_file, "r") as f:
        md_content = f.read()

    # Strip H1 title — WordPress handles title separately
    lines = md_content.split("\n")
    lines = [l for l in lines if not l.startswith("# ")]
    md_content = "\n".join(lines)

    html_content = markdown.markdown(
        md_content,
        extensions=["extra", "toc"]
    )

    # Get metadata from PSV row
    title = row.get("Title", "")
    slug = slugify(title)
    category_string = row.get("Category", "")
    tags_string = row.get("Tags", "")

    print(f"  Title:    {title}")
    print(f"  Slug:     {slug}")
    print(f"  Category: {category_string}")
    print(f"  Tags:     {tags_string}")
    print(f"  Status:   {status}")
    print()

    # Get or create category
    category_id = None
    if category_string:
        print("  📁 Setting up category...")
        category_id = get_or_create_category(category_string)

    # Get or create tags
    tag_ids = []
    if tags_string:
        print("  🏷️  Setting up tags...")
        tag_ids = get_or_create_tags(tags_string)

    # Check for featured media ID from media uploader
    featured_media_id = None
    mediaid_file = os.path.join("drafts", slug + "-mediaid.txt")
    if os.path.exists(mediaid_file):
        with open(mediaid_file, "r") as f:
            try:
                featured_media_id = int(f.read().strip())
                print(f"  🌟 Featured image ID: {featured_media_id}")
            except:
                pass

    # Build post data
    post_data = {
        "title": title,
        "content": html_content,
        "slug": slug,
        "status": status,
    }

    if category_id:
        post_data["categories"] = [category_id]

    if tag_ids:
        post_data["tags"] = tag_ids

    if featured_media_id:
        post_data["featured_media"] = featured_media_id

    # Push to WordPress
    print("  🚀 Pushing to WordPress...")
    response = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts",
        headers=HEADERS,
        json=post_data
    )

    if response.status_code == 201:
        post = response.json()
        print(f"\n  ✅ Success! Post ID: {post['id']}")
        print(f"  🔗 URL: {post['link']}\n")
        return True
    else:
        print(f"\n  ❌ Failed: {response.status_code}")
        print(f"  {response.text}\n")
        return False

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
        print("       SiloGenius WordPress Publisher")
        print("=" * 50)
        print("  1. Publish one article as DRAFT")
        print("  2. Publish one article as LIVE")
        print("  3. Publish all articles as DRAFT")
        print("  4. Publish all articles as LIVE")
        print("  5. Exit")
        print("=" * 50)

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            draft = select_draft()
            if draft:
                publish_article(draft, status="draft")

        elif choice == "2":
            draft = select_draft()
            if draft:
                confirm = input("\n⚠️  Publish LIVE? (yes/no): ").strip().lower()
                if confirm == "yes":
                    publish_article(draft, status="publish")
                else:
                    print("Cancelled.")

        elif choice == "3":
            drafts = [f for f in os.listdir("drafts") if f.endswith(".md")]
            if drafts:
                print(f"\n🚀 Publishing {len(drafts)} articles as DRAFT...\n")
                success = 0
                for i, f in enumerate(drafts, 1):
                    print(f"[{i}/{len(drafts)}]", end="")
                    if publish_article(os.path.join("drafts", f), status="draft"):
                        success += 1
                print(f"\n✅ Done! {success}/{len(drafts)} published as draft.\n")
            else:
                print("\n❌ No drafts found.")

        elif choice == "4":
            drafts = [f for f in os.listdir("drafts") if f.endswith(".md")]
            if drafts:
                confirm = input(f"\n⚠️  Publish ALL {len(drafts)} articles LIVE? (yes/no): ").strip().lower()
                if confirm == "yes":
                    success = 0
                    for i, f in enumerate(drafts, 1):
                        print(f"[{i}/{len(drafts)}]", end="")
                        if publish_article(os.path.join("drafts", f), status="publish"):
                            success += 1
                    print(f"\n✅ Done! {success}/{len(drafts)} published live.\n")
                else:
                    print("Cancelled.")

        elif choice == "5":
            print("\n👋 Goodbye!\n")
            break

        else:
            print("\n❌ Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
