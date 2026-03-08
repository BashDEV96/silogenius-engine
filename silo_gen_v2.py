import os
import json
import time
import sys
import threading
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL")

# Settings
SLEEP_SECONDS = 7
CONTINUE_PROMPT = "Continue the silo. Add more supporting articles in the exact same CSV format. No headers. Pick up right where you left off."

# Spinner class for progress display
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

def load_prompt():
    with open("prompts/silo_prompt.txt", "r") as f:
        return f.read()

def count_rows(text):
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    return max(0, len(lines) - 1)

def clean_output(text):
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if all(c in "|-— " for c in stripped):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

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

def generate_silo(keyword, max_continues):
    prompt = load_prompt()
    full_prompt = prompt.replace("{main_keyword}", keyword)

    print(f"\n🚀 Generating silo for: {keyword}\n")
    print("=" * 50)

    # Start conversation history
    messages = [{"role": "user", "content": full_prompt}]

    # First request
    spinner = Spinner("Pass 1 of {}...".format(max_continues + 1))
    spinner.start()
    output = call_api(messages)
    rows = count_rows(output) if output else 0
    spinner.stop(f"({rows} articles)")

    if not output:
        print("\n❌ Failed to generate silo.")
        return

    full_output = output
    messages.append({"role": "assistant", "content": output})

    # Continuation passes
    for i in range(max_continues):
        pass_num = i + 2
        time.sleep(SLEEP_SECONDS)

        messages.append({"role": "user", "content": CONTINUE_PROMPT})

        spinner = Spinner(f"Pass {pass_num} of {max_continues + 1} total...")
        spinner.start()
        continuation = call_api(messages)

        if not continuation:
            spinner.stop("(failed — stopping)")
            break

        rows = count_rows(full_output + "\n" + continuation)
        spinner.stop(f"({rows} articles so far)")

        full_output += "\n" + continuation.strip()
        messages.append({"role": "assistant", "content": continuation})

    print("=" * 50)

    # Clean output
    full_output = clean_output(full_output)
    total = count_rows(full_output)

    # Save output to CSV file
    filename = os.path.join("silos", keyword.lower().replace(" ", "-") + "-silo.csv")
    with open(filename, "w") as f:
        f.write(full_output)

    print(f"\n✅ Total articles generated: {total}")
    print(f"💾 Saved to: {filename}\n")

if __name__ == "__main__":
    keyword = input("Enter your keyword: ").strip()

    passes_input = input("Total passes? (1-5, default 2): ").strip()
try:
    total_passes = max(1, min(5, int(passes_input)))
except:
    total_passes = 2

generate_silo(keyword, total_passes - 1)
