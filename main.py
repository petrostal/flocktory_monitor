import os
import re
import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from time import sleep

from mail_parser import MailParser

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

SLEEP_INTERVAL = os.getenv('SLEEP_INTERVAL')

LOGIN = os.getenv('LOGIN')
PASSWORD = os.getenv('PASSWORD')

DATA_FILE = os.getcwd() + '/sites'

TG_ADMIN_GROUP = os.getenv('TG_ADMIN_GROUP')
TG_TOKEN = os.getenv('TG_TOKEN')

FLOCKTORY_URL = os.getenv('FLOCKTORY_URL')


def prepare_imap() -> MailParser:
    email_address = os.getenv('EMAIL_USER')
    password = os.getenv('EMAIL_PASSWORD')
    imap_server = os.getenv('EMAIL_HOST')
    mail_parser = MailParser(
        email_address,
        password,
        imap_server,
    )
    return mail_parser


def get_id_from_text(text: str) -> str:
    int_id: str = ''.join(re.findall(r'\d+', text))
    return int_id


def read_data(filename: str = DATA_FILE) -> set:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()


def write_data(data: set, filename: str = DATA_FILE) -> None:
    with open(filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(data))


def notify_admins(message: str) -> None:
    url = (
        f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage?'
        f'chat_id={TG_ADMIN_GROUP}&text={message}'
        f'&parse_mode=markdownv2'
    )
    requests.get(url)


def init_web_driver() -> webdriver:
    options = Options()
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    return webdriver.Chrome(options=options)


def main():
    driver = init_web_driver()
    driver.get(FLOCKTORY_URL)
    wait = WebDriverWait(driver, 30)
    wait.until(
        EC.presence_of_element_located((By.NAME, 'username'))
    ).send_keys(LOGIN)
    wait.until(
        EC.presence_of_element_located((By.NAME, 'password'))
    ).send_keys(PASSWORD)
    wait.until(EC.presence_of_element_located((By.ID, 'kc-login'))).click()
    print('ждём 30 секунд, покуда придёт письмо')
    sleep(30)
    print('всё, проверяем почту')
    mail_parser: MailParser = prepare_imap()
    code: str = mail_parser.check_last_mail(SLEEP_INTERVAL)
    wait.until(EC.presence_of_element_located((By.NAME, 'smsCode'))).send_keys(
        code
    )
    wait.until(EC.presence_of_element_located((By.ID, 'kc-login'))).click()

    elements = wait.until(
        EC.presence_of_all_elements_located(
            (By.CLASS_NAME, 'i-Checkbox-label')
        )
    )
    sitenames = set()
    for element in elements:
        try:
            sitenames.add(element.text.strip().lower())
        except Exception:
            pass

    prev_sites: set = read_data()
    if prev_sites != sitenames:
        changes_set: set = prev_sites ^ sitenames
        changes: str = ''
        for change in changes_set:
            if change in sitenames:
                changes += f'добавился {change}, '
            else:
                changes += f'удалился {change}, '
        changes.rstrip(', ')
        notify_admins(
            'Список сайтов изменился, добавился или удалился '
            f'сайт c ID {changes}'
        )
        print('Список сайтов изменился, ' f'{changes}')
    else:
        notify_admins('Список сайтов не изменился')
        print('Список сайтов не изменился')
    write_data(sitenames)
    # sleep(40)
    driver.quit()


if __name__ == '__main__':
    main()
