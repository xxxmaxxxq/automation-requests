import importlib.util
from pathlib import Path

from playwright.sync_api import sync_playwright


SCRIPT_DIR = Path(__file__).resolve().parent
APP_SCRIPT = SCRIPT_DIR / "create_request copy 2.py"
TRAINING_HTML = SCRIPT_DIR / "training_site.html"


def load_app_module():
    spec = importlib.util.spec_from_file_location("apex_request_app", APP_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    subject = input("Enter training subject, for example KIA QLE SPORTAGE A123BC777: ").strip()
    if not subject:
        subject = "KIA QLE SPORTAGE A123BC777"

    app = load_app_module()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(TRAINING_HTML.as_uri())
        app.fill_request_form(page, subject)
        print("Training form filled. This was local only; no real request was created.")
        input("Press Enter to close the training browser...")
        browser.close()


if __name__ == "__main__":
    main()
