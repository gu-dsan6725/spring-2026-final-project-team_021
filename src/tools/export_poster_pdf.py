from playwright.sync_api import sync_playwright
import pathlib, time

ROOT = pathlib.Path(__file__).resolve().parents[2]

html_path = (ROOT / 'outputs/poster.html').resolve().as_uri()
pdf_path  = str((ROOT / 'outputs/poster.pdf').resolve())

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_viewport_size({"width": 4608, "height": 3456})

    page.goto(html_path, wait_until='networkidle')
    time.sleep(3)

    page.pdf(
        path=pdf_path,
        width='48in',
        height='36in',
        print_background=True,
        margin={'top':'0','right':'0','bottom':'0','left':'0'},
        prefer_css_page_size=True
    )

    browser.close()

print('PDF saved to', pdf_path)