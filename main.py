import requests
import telebot
import logging.config
from jinja2 import Template
# from pprint import pprint
from utils.env import load_params
from utils.logger import logger_config
from utils.utils import HEADERS, TEMPLATE_MESSAGE, TELEGRAM_MANUAL, send_email
app_logger = logging.getLogger('app_logger')


def fetch_wc_url(auth_pair, url, params={}):
    try:
        session = requests.Session()
        session.headers = HEADERS
        r = session.get(url, auth=auth_pair,
                        params=params)
        return r.json()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
        app_logger.exception('Something bad:')


def sanitaze_order_name(order_name):
    return order_name.replace(' (репетиторские услуги)', '')


def fetch_wc_processing_orders(url, auth_pair):
    orders_url = f'{url}/orders'
    params = {
        'status': 'processing'
    }
    wc_processing_orders = fetch_wc_url(auth_pair, orders_url, params)
    if wc_processing_orders:
        orders = []
        for order_info in wc_processing_orders:
            order = {
                'id': order_info['id'],
                'total': order_info['total'],
                'email': order_info['billing']['email'],
                'first_name': order_info['billing']['first_name'],
                'last_name': order_info['billing']['last_name'],
                'files': set(),
                'status': False,
                'products': {}
            }
            for product in order_info['line_items']:
                product_url = f'{url}/products/{product["product_id"]}'
                product_info = fetch_wc_url(auth_pair, product_url)
                if 'downloads' in product_info:
                    for file in product_info['downloads']:
                        order['files'].add(file['file'])
                order['products'][product['product_id']] = {
                    'name': sanitaze_order_name(product['name'])}
                if 'purchase_note' in product_info:
                    order['products'][product['product_id']
                                      ]['purchase_note'] = product_info['purchase_note']
            order['files'] = list(order['files'])
            orders.append(order)
        return(orders)


def send_order(order, webinar_string, params):
    order_info = {'first_name': order['first_name'],
                  'last_name': order['last_name'],
                  'id': order['id'],
                  'webinar_string': webinar_string}
    html = open('email_template.html').read()
    template = Template(html)
    email_message = template.render(**order_info)
    contents = [
        email_message
    ]
    attachments = []
    if 'files' in order:
        attachments = order['files']

    subject = f"Заказ №{order['id']}"
    return send_email(params=params,
                      to_email=order['email'],
                      subject=subject,
                      contents=contents,
                      attachments=attachments)


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
        app_logger.exception('Something bad:')
        return False


def create_result_message(orders) -> str:
    message = ""
    total = 0
    bad_orders = []

    message = "Обработано:\n"

    for order in orders:
        products = ', '.join([product_info['name']
                              for product_id, product_info in order['products'].items()])
        message += f'Заказ №{order["id"]} ({products}) на {order["total"]} руб. \n'
        total += float(order['total'])
        if order['status'] == False:
            bad_orders.append(order)
    if total != orders[0]["total"]:
        message += f'Всего {len(orders)} заказов на {total} руб.'
    if bad_orders:
        bad_orders_id = [bad_order['id'] for bad_order in bad_orders]
        message = f'{message}\nОшибки: {bad_orders_id}'
    return message


def send_result_to_telegram(orders, telegram_bot_token, telegram_users):
    message = create_result_message(orders)
    bot = telebot.TeleBot(telegram_bot_token)
    for user in telegram_users:
        if user:
            bot.send_message(user, message)


def do_orders(orders, auth_pair, url, params):
    for order_number, order in enumerate(orders):
        webinar_string = ''
        webinar_strings = []
        for product_id, product_info in order['products'].items():
            if str(product_id) in params['webinars']:
                product_string = f'<p><b>{product_info["name"]}</b> доступен в закрытом чате.</p>{product_info["purchase_note"]}'
                webinar_strings.append(product_string)
        if webinar_strings:
            webinar_string = "".join(webinar_strings)
            webinar_string = f'{webinar_string} {TELEGRAM_MANUAL}'
            webinar_string = str(''.join(webinar_string.split('\n')))

        send_result = send_order(
            order, webinar_string, params)
        orders[order_number]['send_result'] = send_result
        if send_result:
            orders[order_number]['status'] = change_order_status(
                auth_pair, url, order)
    return orders


def main():
    try:
        logging.config.dictConfig(logger_config)

        params = load_params(
            required_params=[
                'TELEGRAM_BOT_TOKEN',
                'TELEGRAM_USERS_ID',
                'WC_USER_KEY',
                'WC_SECRET_KEY',
                'WC_URL',
                "EMAIL_SENDER",
                "EMAIL_PASSWORD",
                "EMAIL_DISPLAY_NAME",
                "SMTP_SERVER",
                "SMTP_PORT",
                'WEBINARS'
            ])

        auth_pair = (params['wc_user_key'], params['wc_secret_key'])
        url = f'{params["wc_url"]}/wp-json/wc/v3'
        orders = fetch_wc_processing_orders(url, auth_pair)

        if orders:
            orders = do_orders(orders, auth_pair, url, params)
            send_result_to_telegram(
                orders,
                params['telegram_bot_token'],
                params['telegram_users_id'])
    except:
        app_logger.exception('Everything is bad:')


if __name__ == "__main__":
    main()
