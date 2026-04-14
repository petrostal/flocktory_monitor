import os
import re
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from selenium.common.exceptions import TimeoutException
from time import sleep

from mail_parser import MailParser

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

SLEEP_INTERVAL = int(os.getenv('SLEEP_INTERVAL', 5))

LOGIN = os.getenv('LOGIN')
PASSWORD = os.getenv('PASSWORD')

DATA_FILE = os.getcwd() + '/sites'

TG_ADMIN_GROUP = os.getenv('TG_ADMIN_GROUP')
TG_TOKEN = os.getenv('TG_TOKEN')
ROCKET_CHAT_WEBHOOK_URL = os.getenv('ROCKET_CHAT_WEBHOOK_URL')

FLOCKTORY_URL = os.getenv('FLOCKTORY_URL')
FLOCKTORY_AUTH_URL = os.getenv('FLOCKTORY_AUTH_URL')
CODE_INPUT_SELECTOR = (
    'input[name="smsCode"], input[name="code"], '
    'input[name="otp"], input[name="verificationCode"]'
)


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


def print_sites(title: str, sites: set) -> None:
    print(title)
    if not sites:
        print('  <пусто>')
        return
    for site in sorted(sites):
        print(f'  {site}')


def notify_telegram(message: str) -> None:
    if not TG_TOKEN or not TG_ADMIN_GROUP:
        return
    url = (
        f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage?'
        f'chat_id={TG_ADMIN_GROUP}&text={message}'
        f'&parse_mode=markdownv2'
    )
    requests.get(url, timeout=30)


def notify_rocket_chat(message: str) -> None:
    if not ROCKET_CHAT_WEBHOOK_URL:
        return
    requests.post(
        ROCKET_CHAT_WEBHOOK_URL,
        json={'text': message},
        timeout=30,
    )


def notify_admins(message: str) -> None:
    notify_telegram(message)
    notify_rocket_chat(message)


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


def authorize(driver: webdriver, wait: WebDriverWait) -> None:
    driver.get(FLOCKTORY_AUTH_URL)
    mail_parser: MailParser = prepare_imap()
    wait.until(
        EC.presence_of_element_located((By.NAME, 'username'))
    ).send_keys(LOGIN)
    wait.until(
        EC.presence_of_element_located((By.NAME, 'password'))
    ).send_keys(PASSWORD)
    wait.until(EC.presence_of_element_located((By.ID, 'kc-login'))).click()
    code_input = wait.until(wait_for_code_input_or_login_error)
    print('ждём 30 секунд, покуда придёт письмо')
    sleep(30)
    print('всё, проверяем почту')
    code: str = mail_parser.check_last_mail(SLEEP_INTERVAL, max_checks=10)
    if not code:
        raise RuntimeError('Не удалось получить код авторизации из почты')
    print(f'Полученный код авторизации: {code}')
    code_input.send_keys(code)
    submit_button = wait.until(
        EC.presence_of_element_located((By.ID, 'kc-login'))
    )
    submit_button.click()
    wait.until(EC.staleness_of(submit_button))
    try:
        WebDriverWait(driver, 60).until(
            lambda item: urlparse(item.current_url).netloc
            == urlparse(FLOCKTORY_URL).netloc
        )
    except TimeoutException:
        print(f'Не дождались возврата в кабинет. URL: {driver.current_url}')
        print(f'Title: {driver.title}')
        print(f'Body: {driver.find_element(By.TAG_NAME, "body").text[:500]}')
        raise


def wait_for_code_input_or_login_error(driver: webdriver):
    try:
        code_inputs = driver.find_elements(By.CSS_SELECTOR, CODE_INPUT_SELECTOR)
        for code_input in code_inputs:
            if code_input.is_displayed() and code_input.is_enabled():
                return code_input

        body = driver.find_element(By.TAG_NAME, 'body').text
        if 'Security code' in body:
            for item in driver.find_elements(By.TAG_NAME, 'input'):
                input_type = item.get_attribute('type')
                if (
                    item.is_displayed()
                    and item.is_enabled()
                    and input_type not in ('hidden', 'submit', 'button')
                ):
                    return item
        if 'Invalid username or password' in body:
            raise RuntimeError('Flocktory не принял LOGIN/PASSWORD')
    except StaleElementReferenceException:
        return False
    return False


def main():
    driver = init_web_driver()
    try:
        wait = WebDriverWait(driver, 30)
        authorize(driver, wait)
        driver.get(FLOCKTORY_URL)

        try:
            elements = wait.until(
                EC.presence_of_all_elements_located(
                    (By.CLASS_NAME, 'i-Checkbox-label')
                )
            )
        except TimeoutException:
            print(f'Не найден список сайтов. URL: {driver.current_url}')
            print(f'Title: {driver.title}')
            print(f'Body: {driver.find_element(By.TAG_NAME, "body").text[:500]}')
            raise
        sitenames = set()
        for element in elements:
            try:
                sitenames.add(element.text.strip().lower())
            except Exception:
                pass

        prev_sites: set = read_data()
        print_sites('Старый список сайтов:', prev_sites)
        print_sites('Новый список сайтов:', sitenames)
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
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
