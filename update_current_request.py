import os
from pathlib import Path

from playwright.sync_api import sync_playwright


CDP_URL = "http://127.0.0.1:9222"
EMAIL_TO = os.environ.get("SEND_FILE_EMAIL", "docs@example.com")

# Data from the current STS photos in the created folder.
CAR_NUMBER = "A123BC777"
VIN = "XW8ZZZ00ZZZ000000"
BRAND = "KIA"
MODEL = "QLE SPORTAGE"
YEAR = "2017"
STS = "99 08 816629"
OWNER = "ДЖАНДУБАЕВА Н.И."
OWNER_ADDRESS = "*"
OTHER_CAR_NUMBER = "*"
POLICY_NUMBER = "*"
CRASH_DATE_TIME = "25.05.2026 12:00"
INSPECTION_DATE = "31.05.2026"


def current_request_page(context):
    for page in context.pages:
        if "requestedit.htm" in page.url:
            return page
    if context.pages:
        return context.pages[-1]
    return context.new_page()


def set_field(page, selector, value):
    locator = page.locator(selector).first
    locator.wait_for(timeout=15000)
    locator.scroll_into_view_if_needed()
    locator.fill(value)
    locator.evaluate(
        """el => {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }"""
    )
    print(f"Filled {selector}: {value}")


def set_if_exists(page, selector, value, timeout=1500):
    try:
        page.locator(selector).first.wait_for(timeout=timeout)
        set_field(page, selector, value)
        return True
    except Exception:
        print(f"Skip missing field: {selector}")
        return False


def check_full_package_copy(page):
    page.locator("#documents_tab").click()
    page.wait_for_selector("#document_table", timeout=15000)
    checkbox = page.locator(
        "#document_table input[type='checkbox'][onclick*=\"copy_date\"]"
    ).first
    checkbox.wait_for(timeout=10000)
    if not checkbox.is_checked():
        checkbox.click()
        print("Checked full package copy")
    else:
        print("Full package copy already checked")


def save_request(page):
    page.evaluate("page.saveHandler(undefined, 1)")
    page.wait_for_timeout(3000)
    print(f"Saved/request page now: {page.url}")


def choose_apex_option(page, field_id, button_id, container_id, query, option_part):
    field = page.locator(f"#{field_id}").first
    field.wait_for(timeout=15000)
    field.fill(query)
    field.dispatch_event("input")
    page.locator(f"#{button_id}").first.click(force=True)
    page.wait_for_timeout(1500)
    selected = page.evaluate(
        """({containerId, optionPart}) => {
            const container = document.getElementById(containerId);
            if (!container) return false;
            const nodes = Array.from(container.querySelectorAll('*'));
            const node = nodes.find(el => (el.innerText || el.textContent || '').includes(optionPart));
            if (!node) return false;
            node.click();
            return true;
        }""",
        {"containerId": container_id, "optionPart": option_part},
    )
    if not selected:
        raise RuntimeError(f"Option not found for {field_id}: {option_part}")
    page.wait_for_timeout(1000)
    print(f"Selected {field_id}: {field.input_value()}")


def fill_appointment_if_open(page):
    body_text = page.locator("body").inner_text(timeout=10000)
    if "Записаться" not in body_text and "Регион" not in body_text:
        print("Appointment form is not open")
        return

    print("Appointment form detected, filling visit data")
    choose_apex_option(page, "region", "region_button", "region_container", "РО", "Ростовская область")
    choose_apex_option(page, "city", "city_button", "city_container", "Ростов", "Ростов-на-Дону")
    choose_apex_option(page, "street", "street_button", "street_container", "1-й Машиностроитель", "Машиностроитель")
    choose_apex_option(page, "house", "house_button", "house_container", "8", "8")

    set_field(page, "#inspectionDatePart", INSPECTION_DATE)
    page.locator("#morning").check()

    try:
        page.locator("input[value='Записаться']").click(timeout=5000)
        print("Clicked appointment submit")
    except Exception:
        print("Could not click appointment submit")


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = current_request_page(context)
        print(f"Current request page: {page.url}")

        if page.locator("#email").count() == 0:
            fill_appointment_if_open(page)
            print("Done. Appointment page was filled.")
            return

        set_field(page, "#email", EMAIL_TO)
        set_field(page, "#car\\.carNumber", CAR_NUMBER)
        set_field(page, "#car\\.vin", VIN)
        set_field(page, "#car\\.year", YEAR)
        set_field(page, "#car\\.stsPts", STS)
        set_field(page, "#car\\.person\\.name", OWNER)
        set_field(page, "#address", OWNER_ADDRESS)
        set_field(page, "#crashDate", CRASH_DATE_TIME)
        set_field(page, "#car\\.policyNumber", POLICY_NUMBER)

        set_if_exists(page, "#car2\\.carNumber", OTHER_CAR_NUMBER)
        set_if_exists(page, "#car2\\.policyNumber", "*")

        check_full_package_copy(page)
        save_request(page)
        fill_appointment_if_open(page)

        print("Done. Current request was filled without creating a new one.")


if __name__ == "__main__":
    main()
