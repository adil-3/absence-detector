import os
import time
import logging
import traceback

from argparse import ArgumentParser, RawTextHelpFormatter

import telebot

ADMIN_CHAT_IDS = [956138482]


class TelebotExceptionHandler(telebot.ExceptionHandler):
    def handle(self, exception):
        print(f'\tTELEBOT: {exception}\n')
        return True


# A single-threaded application for logging employees' absence times
def detector_app(args):
    from engine.module import AbsenceTracker

    logging.basicConfig(filename=args.LOG_PATH, encoding='utf-8',
                        level=logging.WARNING, format='%(asctime)s %(message)s')

    # Initialize telebot

    import telebot

    telebot.apihelper.RETRY_ON_ERROR = True
    telebot.apihelper.READ_TIMEOUT = 50

    bot = telebot.TeleBot(args.TOKEN, exception_handler=TelebotExceptionHandler())
    bot_users = args.users

    # Check the bot creds

    print('Checking bot credentials...')
    try:
        bot.get_me()
    except (Exception, BaseException):
        print()
        print('The Telegram bot token that you provided seems to be invalid!')
        print('Shutting down...')
        return

    # Check the accounts

    print('Checking Telegram accounts...')
    try:
        for admin in ADMIN_CHAT_IDS:
            message = bot.send_message(admin, '*service_admin*').message_id
            bot.delete_message(admin, message)

        for user in bot_users:
            message = bot.send_message(user, '*service*').message_id
            bot.delete_message(user, message)
    except (Exception, BaseException):
        print()
        print('Some users are unavailable! Make sure you have activated this software copy and that all the '
              'specified users have sent the /start command to the bot.')
        print('Shutting down...')
        return

    print('All set!')
    print()

    # Load the model

    from ultralytics import YOLO

    print('Initializing model...')
    start_model_init = time.time()
    model = YOLO('models/model.pt', task='detect', verbose=args.verbose)

    print(f'Model initialized in {time.time() - start_model_init:.4f} s')

    tracker = AbsenceTracker(model,
                             args.VID_SOURCE, bot,
                             bot_users_ids=args.users,
                             bot_admin_ids=ADMIN_CHAT_IDS, verbose=args.verbose,
                             log_path=args.LOG_PATH, with_telemetry=not args.no_telemetry)
    try:
        while tracker.is_available():
            if must_shutdown():
                msg = 'Shutting down (scheduled)'
                tracker.release_with_telemetry(msg)
                break
            if not tracker.update():
                msg = 'No more data (shutting down)'
                tracker.release_with_telemetry(msg)
                break
        else:
            tracker.send_telemetry('Report: attempted to open an empty stream')
    except (Exception, BaseException):
        msg = 'Tracker is shutting down (:error)'
        tracker.release_with_telemetry(msg)
        traceback.print_exc()

    print('Finished')


def must_shutdown() -> bool:
    return os.path.isfile('terminate.txt')


if __name__ == '__main__':
    parser = ArgumentParser(description='Welcome to Watchmen Absence Detector!\n'
                                        'Authors: Adel Haidar (@adilhaidar)', formatter_class=RawTextHelpFormatter)
    parser.add_argument('LOG_PATH', help='path where the absence logs will be kept')

    stream_source = parser.add_argument('VID_SOURCE', help='video stream source')
    if (source := os.getenv('WM_ABS_SOURCE')) is not None:
        stream_source.nargs = '?'
        stream_source.default = source

    bot_token = parser.add_argument('TOKEN', help='Telegram bot token')
    if (token := os.getenv('WM_ABS_TELEGRAM_BOT_TOKEN')) is not None:
        bot_token.nargs = '?'
        bot_token.default = token

    parser.add_argument('-v', '--verbose', help='enable inference verbosity', action='store_true')
    parser.add_argument('--no-telemetry', help='enable or disable admin telemetry messages within a bot',
                        action='store_true')

    parser.add_argument('--users', required=True, nargs='+', type=int)

    if must_shutdown():
        print('Cannot launch: `terminate.txt` is present')
    else:
        detector_app(parser.parse_args())
