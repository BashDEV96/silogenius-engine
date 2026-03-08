# SiloGenius Engine 🧠⚙️

**The core backend pipeline for the SiloGenius content architecture suite.**

This repository contains the pure Python/CLI engine for generating SEO content silos, writing articles via OpenRouter, generating/processing AI images via Google AI Studio, and publishing directly to WordPress.

> **Looking for the User Interface?**
> Check out the [SiloGenius Web UI](https://github.com/BashDEV96/silogenius-web-ui) repository for the Flask-based frontend that controls this engine.

---

## 🛠 Core Scripts

* **`silo_gen_v2.py`** — Generates complete topical silos and outputs them as CSVs.
* **`article_writer.py`** — Processes the silo CSVs to generate outlines and write full markdown articles.
* **`media_uploader.py` & `media_injector.py`** — Generates AI images, converts them to optimized AVIF format (using `pillow-avif-plugin`), and injects them into the drafted articles.
* **`wp_publisher.py`** — Connects to the WordPress REST API to upload media, create categories/tags, and publish articles (Draft or Live).

## 📂 Directory Structure

```text
silogenius/
├── prompts/            # Tweakable system prompts for AI generation
├── silos/              # Output directory for generated CSV silos
├── outlines/           # Output directory for generated article outlines
├── drafts/             # Output directory for final markdown/HTML articles
└── images/             # Output directory for generated AI images (AVIF)

## 🚀 Setup & Installation

**1. Clone the repository**
```bash
git clone [https://github.com/BashDEV96/silogenius-engine.git](https://github.com/BashDEV96/silogenius-engine.git)
cd silogenius-engine

**2. Create a virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate

**3. Install dependencies**
```bash
pip install -r requirements.txt

**4. Configure Environment**
```bash
cp env.example .env
nano .env
Fill in your API keys (OpenRouter, Google AI Studio) and WordPress credentials (URL, Username, Application Password).

---

## ⚖️ License

SiloGenius Engine is licensed under the **GNU General Public License v3.0**.

You are free to use, modify, and distribute this software. Any modifications must also be released under GPL v3. You may not take this code, modify it, and sell it as a closed-source product.

---
*Part of the open-source SiloGenius suite. Bring Your Own AI. No subscriptions.*