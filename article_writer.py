import os
import json
import time
import sys
import threading
import requests
import csv
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL")

# Settings
SLEEP_SECONDS = 7
CONTINUE_PROMPT_ARTICLE = "Continue writing the article. Pick up exactly where you left off. Same tone, style, and format. No preamble or commentary. Just continue the article."

# Spinner class
class Spinner:
    def __init__(self, message):
        self.message = message
        self.spinning = False
        self.thread = None
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def spin(self):
        i = 0
        while self.spinning:
            sys.stdout.write(f"\r  {self.message} {self.frames[i % len(self.frames)]}")
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1

    def start(self):
        self.spinning = True
        self.thread = threading.Thread(target=self.spin)
        self.thread.daemon = True
        self.thread.start()

    def stop(self, result_msg=""):
        self.spinning = False
        if self.thread:
            self.thread.join()
        sys.stdout.write(f"\r  {self.message} ✓ {result_msg}\n")
        sys.stdout.flush()

def load_prompt(filename):
    with open(filename, "r") as f:
        return f.read()

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

def format_brief(row):
    brief = ""
    for key, value in row.items():
        brief += f"{key}: {value}\n"
    return brief

def call_api(messages):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        stream=True
    )

    if response.status_code == 429:
        time.sleep(30)
        return call_api(messages)

    if response.status_code != 200:
        return None

    output = ""
    try:
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        data = json.loads(line[6:])
                        chunk = data["choices"][0]["delta"].get("content", "")
                        output += chunk
                    except:
                        pass
    except Exception as e:
        pass

    return output

def slugify(title):
    return title.lower().replace(" ", "-").replace("/", "-").replace(":", "").replace("?", "").replace("!", "").replace(",", "").replace("'", "").replace("\"", "")

def find_row_for_outline(outline_filename):
    basename = os.path.basename(outline_filename)
    slug = basename.replace("-outline.md", "")
    all_rows = load_all_rows()
    for row in all_rows:
        title = row.get("Title", "")
        if slugify(title) == slug:
            return row
    return None

def select_csv():
    silos = [f for f in os.listdir("silos") if f.endswith(".csv")]
    if not silos:
        print("\n❌ No CSV files found in silos/ folder.")
        return None
    print("\n📂 Available silo files:")
    for i, f in enumerate(silos, 1):
        print(f"  {i}. {f}")
    choice = input("\nSelect file number: ").strip()
    try:
        return os.path.join("silos", silos[int(choice) - 1])
    except:
        print("❌ Invalid selection.")
        return None

def select_article(rows):
    print("\n📋 Available articles:")
    for i, row in enumerate(rows, 1):
        print(f"  {i}. [{row.get('Article Type', '?')}] {row.get('Title', '?')}")
    choice = input("\nSelect article number: ").strip()
    try:
        return rows[int(choice) - 1]
    except:
        print("❌ Invalid selection.")
        return None

def select_outline():
    outlines = [f for f in os.listdir("outlines") if f.endswith("-outline.md")]
    if not outlines:
        print("\n❌ No outlines found in outlines/ folder. Generate an outline first.")
        return None
    print("\n📋 Available outlines:")
    for i, f in enumerate(outlines, 1):
        display = f.replace("-outline.md", "").replace("-", " ").title()
        print(f"  {i}. {display}")
    choice = input("\nSelect outline number: ").strip()
    try:
        return os.path.join("outlines", outlines[int(choice) - 1])
    except:
        print("❌ Invalid selection.")
        return None

def generate_outline(row, index=None, total=None):
    title = row.get("Title", "")
    prefix = f"[{index}/{total}] " if index and total else ""

    prompt_template = load_prompt("prompts/outline_prompt.txt")
    brief = format_brief(row)
    full_prompt = prompt_template.replace("{article_brief}", brief)

    messages = [{"role": "user", "content": full_prompt}]

    spinner = Spinner(f"{prefix}Outline: {title[:50]}...")
    spinner.start()
    output = call_api(messages)

    if not output:
        spinner.stop("❌ failed")
        return None

    slug = slugify(title)
    filename = os.path.join("outlines", slug + "-outline.md")
    with open(filename, "w") as f:
        f.write(output)

    spinner.stop("✓")
    return filename

def generate_article(row, outline_file=None, index=None, total=None):
    title = row.get("Title", "")
    prefix = f"[{index}/{total}] " if index and total else ""

    # Load outline if provided, otherwise generate one first
    if outline_file and os.path.exists(outline_file):
        with open(outline_file, "r") as f:
            outline = f.read()
    else:
        print(f"\n  ⚠️  No outline found for: {title[:50]} — generating first...")
        time.sleep(SLEEP_SECONDS)
        outline_file = generate_outline(row)
        if not outline_file:
            return
        time.sleep(SLEEP_SECONDS)
        with open(outline_file, "r") as f:
            outline = f.read()

    prompt_template = load_prompt("prompts/article_prompt.txt")
    brief = format_brief(row)
    full_prompt = prompt_template.replace("{article_brief}", brief).replace("{article_outline}", outline)

    messages = [{"role": "user", "content": full_prompt}]

    spinner = Spinner(f"{prefix}Writing: {title[:50]}...")
    spinner.start()
    output = call_api(messages)

    if not output:
        spinner.stop("❌ failed")
        return

    full_article = output
    messages.append({"role": "assistant", "content": output})

    # Continuation loop
    max_continues = 4
    continues = 0
    while continues < max_continues:
        if "## Conclusion" in full_article or "## conclusion" in full_article.lower():
            break

        continues += 1
        spinner.stop(f"continuing ({continues}/{max_continues})...")
        time.sleep(SLEEP_SECONDS)

        messages.append({"role": "user", "content": CONTINUE_PROMPT_ARTICLE})

        spinner = Spinner(f"{prefix}Writing: {title[:50]} (cont {continues})...")
        spinner.start()
        continuation = call_api(messages)

        if not continuation:
            spinner.stop("❌ stream failed")
            break

        full_article += "\n" + continuation.strip()
        messages.append({"role": "assistant", "content": continuation})

    word_count = len(full_article.split())
    spinner.stop(f"{word_count:,} words")

    # Save article
    slug = slugify(title)
    filename = os.path.join("drafts", slug + ".md")
    with open(filename, "w") as f:
        f.write(full_article)

    print(f"  💾 Saved to: {filename}")

def main():
    while True:
        print("\n" + "=" * 50)
        print("       SiloGenius Article Writer")
        print("=" * 50)
        print("  1. Generate outline for one article")
        print("  2. Generate all outlines from a silo")
        print("  3. Write one article")
        print("  4. Write all articles from a silo")
        print("  5. Exit")
        print("=" * 50)

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            csv_file = select_csv()
            if csv_file:
                rows = load_csv(csv_file)
                row = select_article(rows)
                if row:
                    generate_outline(row)

        elif choice == "2":
            csv_file = select_csv()
            if csv_file:
                rows = load_csv(csv_file)
                print(f"\n📝 Generating outlines for {len(rows)} articles...\n")
                for i, row in enumerate(rows, 1):
                    generate_outline(row, index=i, total=len(rows))
                    if i < len(rows):
                        time.sleep(SLEEP_SECONDS)
                print("\n✅ All outlines complete!\n")

        elif choice == "3":
            outline_file = select_outline()
            if outline_file:
                row = find_row_for_outline(outline_file)
                if row:
                    print()
                    generate_article(row, outline_file)
                else:
                    print("\n❌ Could not find matching article brief in silos folder.\n")

        elif choice == "4":
            csv_file = select_csv()
            if csv_file:
                rows = load_csv(csv_file)
                print(f"\n✍️  Writing {len(rows)} articles...\n")
                for i, row in enumerate(rows, 1):
                    slug = slugify(row.get("Title", "article"))
                    outline_file = os.path.join("outlines", slug + "-outline.md")
                    generate_article(row, outline_file, index=i, total=len(rows))
                    if i < len(rows):
                        time.sleep(SLEEP_SECONDS)
                print("\n✅ All articles complete!\n")

        elif choice == "5":
            print("\n👋 Goodbye!\n")
            break

        else:
            print("\n❌ Invalid choice. Please try again.")

if __name__ == "__main__":
    main()
