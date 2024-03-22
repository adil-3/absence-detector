import logging
import time
import traceback
from io import BytesIO

import ultralytics.engine.model as engine
import ultralytics.engine.results as results_collection

from engine.config import *
from engine.messages import *

LOGGER = logging.getLogger('WM_ABS_DETECT')


def to_photo(image):
    _, buf = cv2.imencode('.jpg', image)
    return BytesIO(buf)


class AbsenceTracker:
    def __init__(self, model: engine.Model, cap_addr, bot_instance,
                 bot_users_ids: list,
                 bot_admin_ids: list, verbose=False,
                 log_path='absence.log', with_telemetry=True):
        self.bot_admin_ids = bot_admin_ids
        self.bot_alarm_ids = bot_users_ids

        self.bot = bot_instance
        # self.bot_init()
        self.with_telemetry = with_telemetry

        self.model = model

        # Counters
        self.cnt_f = 0
        self.abs_cnt = 0
        self.last_sent = 0

        # Logging
        self.log_inference = verbose
        logging.basicConfig(filename=log_path, encoding='utf-8',
                            level=logging.WARNING, format='%(asctime)s %(message)s')

        # Timekeeping
        self.last_seen = time.time()
        print(self.last_seen)

        self.current_frame = None
        self.stopped = True

        # Capturing
        try:
            self.capture = cv2.VideoCapture(cap_addr)
            self.stopped = False

            ret, self.input = self.capture.read()
            if ret:
                print(f'New stream opened with resolution {self.input.shape[1::-1]}')
            else:
                msg = 'Video source is unavailable'
                LOGGER.error(msg)
                print(msg)

            msg = 'System is ready'
            for admin in self.bot_admin_ids:
                self.bot.send_message(admin, msg)

            LOGGER.warning(msg)  # use warnings instead of debug for cleaner logs
            print(msg)
            print()
        except KeyboardInterrupt:
            self.release_with_telemetry('Shutting down (on demand)...')

    def __del__(self):
        msg = '\tInternal: Stream closed\n'
        self.release_with_telemetry(msg)

    def update(self) -> bool:
        try:
            self._retrieve()
            self._update()
        except KeyboardInterrupt:
            msg = 'Tracker is shutting down (:force)'
            self.release_with_telemetry(msg)
        except Exception as e:
            LOGGER.error(f'Error: {e}')

            msg = f'Error: {type(e).__name__}'
            self.release_with_telemetry(msg, include_image=False)

            self.stopped = True

            traceback.print_exc()

        return not self.stopped

    def _update(self):
        if self._cnt_trigger:
            results = self._process_frame()

            if self.stopped or results is None:
                return

            self.current_frame = results.plot()
            boxes = results.boxes

            if not boxes:
                self.on_absence()
            else:
                self.on_return(boxes)

            self.telemetry()

        self._cnt_update()

    def on_return(self, boxes):
        _ids = boxes.id

        if self.abs_cnt:
            report = MSG_OBJECT_RETURNED
            if _ids:
                report += f' IDs: {_ids}'

            LOGGER.warning(report)

            # User alarm
            self.send_notification(report)

            self.send_telemetry('CURRENT VIEW', self.input)
            self.send_telemetry(report, self.current_frame)

        self.last_seen = time.time()
        self.abs_cnt = 0

    def on_absence(self):
        dt = time.time() - self.last_seen
        dt_minutes = dt // 60
        al_minutes = ABS_ALERT_MINUTES + self.abs_cnt

        dur_caption = time.strftime("%H:%M:%S", time.gmtime(dt))
        cv2.putText(self.current_frame,
                    f'NOBODY DETECTED ({dur_caption})',
                    org, font, fontScale, color[::-1], thickness, cv2.LINE_AA)

        if dt_minutes >= al_minutes:
            report = MSG_OBJECT_LEFT.format(al_minutes)
            if dt_minutes == ABS_ALERT_MINUTES:
                LOGGER.warning(report)

                # User alarm
                self.send_notification(report)

                self.send_telemetry('CURRENT VIEW', self.input)
                self.send_telemetry(report, self.current_frame)

            self.abs_cnt = (self.abs_cnt + 1) % 1_000_000

    def is_available(self) -> bool:
        return not self.stopped and self.capture.isOpened()

    def send_telemetry(self, message, image=None):
        try:
            if image is not None and image.any():
                for admin in self.bot_admin_ids:
                    self.bot.send_photo(admin, to_photo(image), message)
            else:
                for admin in self.bot_admin_ids:
                    self.bot.send_message(admin, message)
            self.last_sent = time.time()
        except Exception as te:
            if hasattr(te, 'result_json'):
                LOGGER.error(f'Error: Telegram server cannot be reached. (Wrong token?, etc) {te}')
                print('Telegram error occurred (check the logs)')
                print()

                print('Cannot continue')
                return

    def send_notification(self, message):
        try:
            for user in self.bot_alarm_ids:
                self.bot.send_message(user, message)
        except Exception as te:
            if hasattr(te, 'result_json'):
                LOGGER.error(f'Error: Telegram server cannot be reached. (Wrong token?, etc) {te}')
                print('Telegram error occurred (check the logs)')
                print()

                print('Cannot continue')
                return

    def telemetry(self):
        if self.with_telemetry and (time.time() - self.last_sent) // 60 >= TELEMETRY_MINUTES:
            self.send_telemetry('TELEMETRY', self.current_frame)
            self.send_telemetry('TELEMETRY', self.input)
            self.last_sent = time.time()

    def release(self, msg):
        if hasattr(self, 'capture'):
            self.capture.release()
        print(msg)

    def release_with_telemetry(self, msg, include_image=True):
        self.release(msg)
        self.send_telemetry(msg, self.input if include_image and hasattr(self, 'input') else None)

    def _cnt_trigger(self) -> bool:
        return self.cnt_f % NFRAMES == 0

    def _cnt_update(self):
        self.cnt_f = (self.cnt_f + 1) % CNT_RESET

    def _retrieve(self) -> bool:
        try:
            result, self.input = self.capture.read()
            return result
        except KeyboardInterrupt:
            msg = 'Tracker is shutting down (:retrieve)'
            self.release_with_telemetry(msg)

    def _process_frame(self) -> results_collection.Results | None:
        try:
            frame = cv2.resize(self.input[region[0]:region[1], region[2]:region[3]], ISIZE)
            return self.model(frame, classes=0, verbose=self.log_inference)[0]
        except KeyboardInterrupt:
            msg = 'Tracker is shutting down (:process)'
            self.stopped = True
            self.release_with_telemetry(msg)
        except (Exception, BaseException):
            self.send_telemetry("Report: 1 frame dropped")
            return None
