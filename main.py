import requests
import yagmail
import smtplib
import logging
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
    except:
        print(f'Error {url}')
        return None


def fetch_wc_processing_orders(url, auth_pair):
    orders_url = f'{url}/orders'
    params = {
        'status': 'processing'
    }
    wc_processing_orders = fetch_wc_url(auth_pair, orders_url, params)
    if wc_processing_orders:
        try:
            orders = []
            for order_info in wc_processing_orders:

                # debug!
                if order_info['billing']['email'] != 'dimk00z@gmail.com':
                    continue

                order = {
                    'id': order_info['id'],
                    'total': order_info['total'],
                    'email': order_info['billing']['email'],
                    'first_name': order_info['billing']['first_name'],
                    'last_name': order_info['billing']['last_name'],
                }
                order['files'] = set()
                for product in order_info['line_items']:
                    product_url = f'{url}/products/{product["product_id"]}'
                    product_info = fetch_wc_url(auth_pair, product_url)
                    for file in product_info['downloads']:
                        order['files'].add(file['file'])
                order['files'] = list(order['files'])
                orders.append(order)
            return(orders)
        except:
            print(f'Error {url}')
            return None


def send_email(order, email_user, email_password):
    user_info = {'first_name': order['first_name'],
                 'last_name': order['last_name'],
                 'id': order['id']}
    email_message = TEMPLATE_MESSAGE.format(**user_info)
    print(email_message)
    try:
        yag = yagmail.SMTP(user={email_user: "4languagetutors.ru"}, password=email_password,
                           smtp_ssl=True,
                           host='smtp.yandex.ru', port=465)
        contents = [
            email_message
        ]
        for file_name in order['files']:
            # debug
            if '.zip' in file_name:
                continue
            # debug
            contents.append(file_name)

        subject = f"Заказ №{order['id']}"
        yag.send(order['email'], subject, contents)
        return True
    except (YagInvalidEmailAddress, YagConnectionClosed,
            YagAddressError, smtplib.SMTPDataError, smtplib.SMTPServerDisconnected) as ex:
        print(ex)
        return False


def change_order_status(auth_pair, url, order):
    pass


def send_result_to_telegram(orders, telegram_bot_token, telegram_users):
    pass


def do_orders(orders, auth_pair, url, email_user, email_password):
    for order_number, order in enumerate(orders):
        send_result = send_email(
            order, email_user, email_password)
        orders[order_number]['send_result'] = send_result
        if send_result:
            change_order_status(auth_pair, url, order)
            # debug
        break


def main():
    logging.basicConfig(level=logging.DEBUG)
    params = load_params()
    auth_pair = (params['wc_user_key'], params['wc_secret_key'])
    url = f'{params["wc_url"]}/wp-json/wc/v3'
    orders = fetch_wc_processing_orders(url, auth_pair)
    pprint(orders)
    do_orders(orders, auth_pair, url,
              params["email_sender"], params["email_password"])


if __name__ == "__main__":
    main()
