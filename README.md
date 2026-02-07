<div align="center">
  <img src="https://github.com/Pearl-Solutions/.github/blob/main/Pearl_Solutions__Tavola_disegno_1-02.png?raw=true" alt="Pearl Solutions Group Banner" />
</div>

<div align="center">
  <h1>Amazon Toolbox</h1>
  <p>
    <strong>CLI toolbox to manage Amazon accounts and automate raffle workflows.</strong><br>
    Generate accounts, open browser sessions, enter raffles, and check invitations from a single menu-driven interface.
  </p>
</div>

---

## Overview

**Amazon Toolbox** is a **Python 3** command-line tool designed to manage Amazon accounts and streamline raffle-related workflows (entry + invitation checks) with a simple interactive menu.

The project is built with the following principles:
- automation-first
- CLI-oriented workflows
- minimal dependencies
- reproducible configuration
- scalable across multiple accounts/proxies

---

## Key Features

- **Account generator** (bulk, multi-threaded)
- **Account browser opener** (open a saved account session and keep it running)
- **Raffle entry** (submit invite requests for one or many ASINs)
- **Invitation checker** (scan mailbox and export results to CSV)
- Structured outputs (**CSV** and local account storage)
- Defensive error handling

---

## Prerequisites

- **Python 3.13+**
- A working **IMAP mailbox** (used to retrieve verification/OTP emails)
- A valid **SMS provider API key** (SMSPool)
- Proxies (recommended for multi-account workflows)
- CLI access (Windows/macOS/Linux)

---

## Installation
```bash
git clone https://github.com/pearl-solutions/pearl-solutions-amazon.git
cd pearl-solutions-amazon
```

```bash
pip install -r requirements.txt
```
### Camoufox browser download (required)
This project uses **Camoufox** for browser automation. You must download the Camoufox browser once.

**On Windows:**
```bash
camoufox fetch
```
If the command is not found, try:
```bash
python -m camoufox fetch
```
**On macOS / Linux:**
Follow the official installation guide:
https://camoufox.com/python/installation/#download-the-browser

---

## Configuration

The tool uses a `config.json` file at the project root.

On first run, if `config.json` does not exist, it will be created and the program will exit so you can fill it in.

### `config.json` fields

| Key | Description |
| --- | --- |
| `webhook` | Discord webhook URL used for notifications (if enabled) |
| `sms_pool` | SMSPool API key (Bearer auth) |
| `imap.email` | IMAP mailbox login/email |
| `imap.password` | IMAP password (or app password) |
| `imap.server` | IMAP server hostname |
| `imap.port` | IMAP SSL port (default: `993`) |
| `amazon_asins` | List of ASINs used by raffle entry/check flows |

---

## Usage

### Basic Execution

Run the CLI menu:
```bash
python main.py
```
You will see a menu similar to:
- Generate account
- Open account browser
- Enter raffle
- Check for invitations
- Settings

### CLI Prompts (Generator)

When generating accounts, the tool will prompt you for:
- an **email file** (one email per line)
- a **proxy file** (one proxy per line)
- number of **threads**
- number of **accounts** to generate
- the account **password**

Expected proxy format (typical):
```text
ip:port:user:pass
```
---

## Example Run
```text
Welcome to our new Amazon accounts manager, 10 accounts loaded, 3 products loaded.

 (1) Generate account
 (2) Open account browser
 (3) Enter raffle
 (4) Check for invitations
 (5) Settings
 (6) Exit
```
---

## Output

### Saved accounts
Generated accounts are persisted locally (see the `.accounts/` directory).  
This allows the rest of the modules (opener / raffle entry / checks) to reuse existing sessions.

### Invitation exports (CSV)
Invitation checks and some raffle workflows export timestamped CSV files:
```text
invitations-YYYY-MM-DD-HH-MM-SS.csv
```
CSV columns:
```text
email, item, link, asin
```
---

## Troubleshooting

Common failure cases:
- `config.json` missing or incomplete (the tool will print which fields are missing)
- IMAP login failure (wrong server/password, app-password required, mailbox security rules)
- Proxies timing out or blocked (try replacing proxies or reducing concurrency)
- External service/API instability (SMS provider, Amazon endpoints)

All errors are surfaced via CLI output.

---

## Contributing

Contributions are welcome.

### How to contribute
1. Fork the repository
2. Create a feature branch:
   ```bash
   git checkout -b feat/my-change
   ```
3. Make your changes (keep formatting consistent and add docstrings/comments where relevant)
4. Test your changes locally
5. Open a Pull Request with:
   - what you changed
   - how to reproduce/test
   - any screenshots/log snippets if it affects CLI behavior

### Guidelines
- Keep behavior backwards-compatible unless discussed in an issue first
- Avoid committing secrets (API keys, proxies, emails, cookies)
- Prefer small, focused PRs

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Disclaimer

This project is intended for controlled, authorized usage only. Responsibility for compliance, permissions, and downstream use lies entirely with the user.

---

<div align="center">
  <sub>© 2026 Amazon Toolbox. Made by Pearl Solutions Group</sub>
</div>
