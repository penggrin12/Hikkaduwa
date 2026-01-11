# Hikkaduwa Userbot 

Hikkaduwa is a powerful and modular Telegram userbot. This fork, maintained by [Penggrin](https://github.com/penggrin12), aims to be a **lightweight version** of the upstream Hikka project developed by [Dan Gazizullin (hikariatama)](https://t.me/hikariatama).

![Lines of code](https://img.shields.io/endpoint?url=https://ghloc.vercel.app/api/penggrin12/Hikkaduwa/badge?filter=.py$&style=flat&logoColor=white&label=Lines%20of%20Code)
![GitHub Open issues](https://img.shields.io/github/issues/penggrin12/Hikkaduwa)
![GitHub Closed pull requests](https://img.shields.io/github/issues-pr-closed/penggrin12/Hikkaduwa)  
![Python Version](https://img.shields.io/badge/python-3.9+-blue)
![License](https://img.shields.io/badge/license-AGPLv3-red)


## Key Features

* **Modular Architecture:** Easily extend functionality by loading custom modules.
* **Inline Features:** Supports inline forms, galleries, lists, and custom inline command handlers via its own bot.
* **Configuration System:** Interactive configuration for modules and core settings (`.config` command).
* **Terminal Access:** Execute shell commands directly from Telegram.
* **API Rate Limiting:** Built-in protection against hitting Telegram API limits.
* **Code Evaluation:** Evaluate Python code on the fly.
* **Advanced Logging:** Configurable logging levels and Telegram log forwarding.
* **Help System:** Get help for specific modules or list all available commands.
* **Translations:** Supports multiple languages through language packs.
* **Aliases:** Create custom shortcuts for commands.
* **Watchers:** Automate actions based on incoming/outgoing messages with various filters.

## Requirements

* **Python:** 3.9 or higher (haven't yet tested on <3.12)
* **UV:** The `uv` package installer is recommended ([Installation Guide](https://github.com/astral-sh/uv#installation)).
* **Telegram API Credentials:** API ID and API Hash from <https://my.telegram.org>.
* **Dependencies:** See `pyproject.toml` for the full list (includes `telethon`, `aiogram`, `requests`, etc.). These are installed automatically by `uv`.
* **FFMPEG:** (Optional) Required by some modules for media processing.

## Installation & Setup

1.  **Install `uv` (if you haven't already):**
    Follow the official `uv` [installation instructions](https://github.com/astral-sh/uv#installation). A common method is:
    ```bash
    # Linux/macOS
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Windows (requires Python installed)
    pip install uv
    # Or see other methods like pipx, brew, etc. in the uv docs
    ```
2.  **Clone the repository:**
    ```bash
    git clone https://github.com/penggrin12/Hikkaduwa.git
    cd Hikkaduwa
    ```
3.  **Create and activate a virtual environment:**
    ```bash
    uv sync
    ```
4.  **Run:**
    * Run the userbot for the first time:
        ```bash
        uv run python -m hikka
        ```
    * Follow the on-screen instructions to enter your Telegram API ID and API Hash.
    * Then, You will be prompted to log in using either your phone number or a QR code.

## Basic Usage

* **Command Prefix:** By default, commands start with `.` (e.g., `.help`, `.ping`). This can be changed using `.setprefix`.
* **Inline Bot:** Use the userbot's features inline by mentioning its associated bot username (obtained during setup or via `.ch_hikka_bot`).
* **Help:** Use the `.help` command to see available modules and commands. Use `.help <module_name>` for specific module help.
* **Configuration:** Use the `.config` command for an interactive menu to configure modules and core settings.

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**. See the [LICENSE](https://www.gnu.org/licenses/agpl-3.0.html) file for details.

## Authors & Credits

* **Fork Developer:** [Penggrin](https://github.com/penggrin12)
* **Upstream GitHub Repository:** [https://github.com/beveiled/hikka](https://github.com/beveiled/hikka)
* **Upstream Developer:** [Dan Gazizullin (hikariatama)](https://t.me/hikariatama)
