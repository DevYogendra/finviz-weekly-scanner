# Security

- Real Finviz URLs, cookies, browser profiles, email credentials, screenshots, logs, runtime data, and SQLite databases are ignored by Git.
- Logs redact common token, cookie, password, and secret patterns.
- The scanner does not reverse engineer private Finviz endpoints and does not bypass CAPTCHA or login controls.
- Scheduled task arguments contain paths only, not passwords.
- Email notification is disabled until configured externally.
