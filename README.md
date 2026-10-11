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
EMAIL_SMTP_LOGIN=
```

`EMAIL_SMTP_LOGIN` — необязательный логин для SMTP-авторизации. Если он не задан
или пустой, используется `EMAIL_SENDER`, как в текущей настройке Яндекса.
`EMAIL_SENDER` задаёт адрес отправителя, а `EMAIL_DISPLAY_NAME` — его имя.

### Отправка через Selectel

Укажите SMTP-реквизиты из панели управления Selectel:

```dotenv
EMAIL_SENDER=sender@example.com
EMAIL_DISPLAY_NAME=Название магазина
EMAIL_SMTP_LOGIN=selectel-login
EMAIL_PASSWORD=selectel-password
EMAIL_SMTP_SERVER=smtp.mail.selcloud.ru
EMAIL_SMTP_PORT=1127
```

Адрес отправителя должен принадлежать домену, подключённому к почтовому сервису
Selectel со статусом `Verified`. Используется SSL на порту `1127`; подключение
через STARTTLS на порту `1126` не поддерживается. Устанавливать sSMTP не нужно:
приложение подключается к SMTP-серверу напрямую.

### Проверка

Тесты подменяют SMTP-соединение и не отправляют реальные письма:

```sh
python -m unittest discover -s tests -v
```

### Запуск

Для выполнения скрипта использовал cron:
```
*/30 * * * * cd /home/Woo-sender/ && /home/Woo-sender/env/bin/python /home/Woo-sender/main.py
```
