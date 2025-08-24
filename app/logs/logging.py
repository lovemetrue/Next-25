import os
import sys
from loguru import logger

LOG_OUTPUT_PATH = os.path.join("logs/bot.log")
LOG_FORMAT = ("<green>{time:YYYY.MM.DD HH:mm:ss.SSS zz}</green> | "
              "<level>{level: <8}</level> | <yellow>Line {line: >4} "
              "({file}):</yellow> <b>{message}</b>")


if not os.path.exists("logs"):
    os.makedirs("logs")
    logger.error(f"Не удалось создать директорию logs. Продолжаем работу с текущей директорией.")
    sys.exit(1)


# def logging(message):
#     """
#     Логирование в logs/bot.log юзернейма и отправленного сообщения пользователем.
#     :param message:
#     :return:
#     """
#     logger.add("logs/Next'25.log", format=LOG_FORMAT, colorize=False, backtrace=True, diagnose=True)
#     logger.info(f"Пользователь: {message.from_user.username}")
#     logger.info(f"Отправил сообщение: {message.text}")
