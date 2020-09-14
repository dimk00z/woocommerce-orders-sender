import requests
import yagmail
import smtplib
import logging
import telebot
from utils import HEADERS, TEMPLATE_MESSAGE, load_params
from yagmail.error import YagInvalidEmailAddress, YagConnectionClosed, YagAddressError
from pprint import pprint


def fetch_wc_url(auth_pair, url, params={}):
    try:
        session = requests.Session()
        session.headers = HEADERS
        r = session.get(url, auth=auth_pair,
                        params=params)
        return r.json()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
        print("Connection error:", error)


def fetch_wc_processing_orders(url, auth_pair):
    orders_url = f'{url}/orders'
    params = {
        'status': 'processing'
    }
    wc_processing_orders = fetch_wc_url(auth_pair, orders_url, params)
    if wc_processing_orders:
        orders = []
        for order_info in wc_processing_orders:

            # debug!
            # if order_info['billing']['email'] != 'dimk0z@yandex.ru':
            #     continue

            order = {
                'id': order_info['id'],
                'total': order_info['total'],
                'email': order_info['billing']['email'],
                'first_name': order_info['billing']['first_name'],
                'last_name': order_info['billing']['last_name'],
                'files': set(),
                'status': False
            }
            for product in order_info['line_items']:
                product_url = f'{url}/products/{product["product_id"]}'
                product_info = fetch_wc_url(auth_pair, product_url)
                for file in product_info['downloads']:
                    order['files'].add(file['file'])
            order['files'] = list(order['files'])
            orders.append(order)
        return(orders)


def send_email(order, email_user, email_password, email_display_name):
    user_info = {'first_name': order['first_name'],
                 'last_name': order['last_name'],
                 'id': order['id']}
    email_message = TEMPLATE_MESSAGE.format(**user_info)
    try:
        yag = yagmail.SMTP(user={email_user: email_display_name},
                           password=email_password,
                           smtp_ssl=True,
                           host='smtp.yandex.ru', port=465)
        contents = [
            email_message
        ]
        for file_name in order['files']:
            contents.append(file_name)
        subject = f"Заказ №{order['id']}"
        yag.send(to=order['email'], subject=subject, contents=contents)
        return True
    except (YagInvalidEmailAddress, YagConnectionClosed, smtplib.SMTPAuthenticationError,
            YagAddressError, smtplib.SMTPDataError, smtplib.SMTPServerDisconnected) as ex:
        print(ex)
        return False


def change_order_status(auth_pair, url, order):
    try:
        put_url = f'{url}/orders/{order["id"]}'
        session = requests.Session()
        session.headers = HEADERS
        r = session.put(put_url, auth=auth_pair,
                        params={"status": "completed"})
        if r.status_code == 200:
            return True
        else:
            return False
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
        print("Connection error:", error)
        return False


def send_result_to_telegram(orders, telegram_bot_token, telegram_users):
    message = ""
    total = 0
    bad_orders = []
    ids_orders = [order['id'] for order in orders]
    for order in orders:
        total += float(order['total'])
        if order['status'] == False:
            bad_orders.append(order)
    message = f"Обработано {len(orders)} заказов на {total} руб."
    message = f'{message}\n {ids_orders.__repr__()}'
    if bad_orders:
        message = f'{message}\nОшибки: {ids_orders.__repr__()}'

    bot = telebot.TeleBot(telegram_bot_token)
    for user in telegram_users:
        bot.send_message(user, message)


def do_orders(orders, auth_pair, url, params):
    for order_number, order in enumerate(orders):
        send_result = send_email(
            order, params['email_sender'], params["email_password"], params["email_display_name"])
        orders[order_number]['send_result'] = send_result
        if send_result:
            orders[order_number]['status'] = change_order_status(
                auth_pair, url, order)
    return orders


def main():
    # logging.basicConfig(level=logging.DEBUG)
    params = load_params()
    auth_pair = (params['wc_user_key'], params['wc_secret_key'])
    url = f'{params["wc_url"]}/wp-json/wc/v3'
    orders = fetch_wc_processing_orders(url, auth_pair)
    if orders:
        orders = do_orders(orders, auth_pair, url, params)
        send_result_to_telegram(
            orders,
            params['telegram_bot_token'],
            params['telegram_users'])


if __name__ == "__main__":
    main()
