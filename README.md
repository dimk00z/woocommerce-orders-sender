# WooCommerce-file-sender
## Описание 
Данный скрип был написан для автоматизации рассылки файлов по заказам из WooCommerce.
Необходимость возникла при понимании, что не все пользователи в состоянии самостоятельно скачать файлы по генерируемым ссылкам.

Скрипт собирает заказы со статусом `processing` и рассылает письма с файлами. 

По выполнению приходит отчет в телеграм.

## Настройка и выполнение

Работоспособноть проверена на Python 3.8+. 
Установка зависимостей `pip install -r requirements.txt`

Для работы необходимо наличие .env файла:
```
TELEGRAM_BOT_TOKEN=
TELEGRAM_USERS_ID=[""]
WC_USER_KEY=
WC_SECRET_KEY=
WC_URL=
EMAIL_SENDER=
EMAIL_PASSWORD=
EMAIL_DISPLAY_NAME=
EMAIL_SMTP_SERVER=smtp.yandex.ru
EMAIL_SMTP_PORT=465
```
Для выполнения скрипта использовал cron:
```
*/30 * * * * cd /home/Woo-sender/ && /home/Woo-sender/env/bin/python /home/Woo-sender/main.py
```