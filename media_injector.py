import os
import re
import csv
from urllib.parse import quote

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

def get_inline_image_count(article_size):
    """Determine inline image count from article size string"""
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

def build_pollinations_url(prompt, width=1200, height=630):
    """Build a Pollinations image URL from a prompt"""
    encoded = quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true"

def generate_featured_url(title):
    prompt = f"{title} hero image professional digital art"
    return build_pollinations_url(prompt)

def generate_inline_url(title, section_heading):
    prompt = f"{title} {section_heading} professional illustration"
    return build_pollinations_url(prompt, width=1000, height=500)

def get_h2_sections(lines):
    """Find H2 section line indices, excluding FAQ, Key Takeaways, Conclusion"""
    skip = ["faq", "key takeaways", "conclusion", "frequently asked"]
    sections = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            if not any(s in heading for s in skip):
                sections.append((i, line[3:].strip()))
    return sections

def inject_media(draft_file):
    print(f"\n🖼️  Injecting media: {os.path.basename(draft_file)}\n")
    print("-" * 50)

    # Find matching PSV row
    row = find_row_for_draft(draft_file)
    if not row:
        print("❌ Could not find matching PSV row.")
        return

    title = row.get("Title", "")
    article_size = row.get("Article Size", "")
    inline_count = get_inline_image_count(article_size)

    print(f"  Title:         {title}")
    print(f"  Article Size:  {article_size}")
    print(f"  Inline Images: {inline_count}")
    print()

    # Read markdown
    with open(draft_file, "r") as f:
        content = f.read()

    lines = content.split("\n")

    # Generate and save featured image URL separately
    featured_url = generate_featured_url(title)
    slug = slugify(title)
    featured_file = os.path.join("drafts", slug + "-featured.txt")
    with open(featured_file, "w") as f:
        f.write(featured_url)
    print(f"  ✅ Featured image URL saved to: {slug}-featured.txt")

    # Find eligible H2 sections for inline image placement
    sections = get_h2_sections(lines)

    if not sections:
        print("  ⚠️  No eligible H2 sections found for inline images.")
        return

    # Pick evenly spaced injection points
    if inline_count >= len(sections):
        injection_indices = [s[0] for s in sections]
    else:
        step = len(sections) / inline_count
        injection_indices = [sections[int(i * step)][0] for i in range(inline_count)]
        section_headings = [sections[int(i * step)][1] for i in range(inline_count)]

    # Build inline image tags
    image_tags = []
    for i, heading in enumerate(section_headings):
        url = generate_inline_url(title, heading)
        alt_text = f"{title} - {heading}"
        tag = f"\n![{alt_text}]({url})\n"
        image_tags.append((injection_indices[i], tag))

    # Inject images after the H2 line — insert in reverse order to preserve line numbers
    for line_index, tag in sorted(image_tags, reverse=True):
        lines.insert(line_index + 1, tag)

    # Save updated markdown
    updated_content = "\n".join(lines)
    with open(draft_file, "w") as f:
        f.write(updated_content)

    print(f"  ✅ {inline_count} inline images injected into article")
    print(f"  💾 Saved to: {os.path.basename(draft_file)}\n")

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
        print("       SiloGenius Media Injector")
        print("=" * 50)
        print("  1. Inject media into one article")
        print("  2. Inject media into all articles")
        print("  3. Exit")
        print("=" * 50)

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            draft = select_draft()
            if draft:
                inject_media(draft)

        elif choice == "2":
            drafts = [f for f in os.listdir("drafts") if f.endswith(".md")]
            if drafts:
                print(f"\n🖼️  Injecting media into {len(drafts)} articles...\n")
                for i, f in enumerate(drafts, 1):
                    print(f"  [{i}/{len(drafts)}]", end="")
                    inject_media(os.path.join("drafts", f))
                print("\n✅ All articles done!\n")
            else:
                print("\n❌ No drafts found.")

        elif choice == "3":
            print("\n👋 Goodbye!\n")
            break

        else:
            print("\n❌ Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
