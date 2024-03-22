# Watchmen absence detector

An application for logging watchmen's absence in real time with optional Telegram bot telemetry.

## Installation

You are going to need Python 3.12 or later. Use [conda](https://docs.anaconda.com/free/miniconda/miniconda-install/) for
convenience.

```commandline
pip install -r requirements.txt
```

## Usage

In a configured environment (with all variables set), you only need to provide the logging path and user CHAT_IDs:

```
python app.py [-h] [-v] [--no-telemetry] --users USERS [USERS ...] LOG_PATH [VID_SOURCE] [TOKEN]
```

### Environment

To use the shorter call syntax, you'll need to provide the following environment variables:

```
export WM_ABS_SOURCE
export WM_ABS_TELEGRAM_BOT_TOKEN
```

You can also set it up in a specific [file](credentials/setenv.sh).
To temporarily configure the environment for the current session, use the following command:

```commandline
source credentials/setenv.sh
```

## License

This project is licensed under the [Apache 2.0 License](https://opensource.org/license/apache-2-0), see the [LICENSE](LICENSE) file.

## Authors

Adel Haidar ([@adilhaidar](https://t.me/adilhaidar))