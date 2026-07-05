# Troubleshooting

- Configuration missing: run `finviz-scanner configure`.
- Playwright missing: run `python -m playwright install chromium`.
- Count mismatch: open the saved screenshots and HTML under the failed run working directory, then retry headed.
- CAPTCHA or login challenge: run `finviz-scanner scan --headed` and resolve the challenge manually. The scanner does not bypass CAPTCHA.
- Selector breakage: update `src/finviz_scanner/extraction/finviz_dom.py` and add a sanitized fixture proving the new layout.
- Unresolved exchange: update the local `symbol-master.csv`; the scanner will not guess.
- Scheduled task not running: inspect Windows Task Scheduler history and logs under the output `logs` directory.
