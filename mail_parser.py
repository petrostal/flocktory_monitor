import base64
import email
import email.header
import email.message
import imaplib
import os
import sys
from time import sleep


class MailParser:
    UID_FILE = 'last.uid'

    def __init__(
        self,
        email_address: str,
        password: str,
        imap_server: str,
    ):
        self.imap = imaplib.IMAP4_SSL(imap_server)
        self.imap.login(email_address, password)
        result = self.imap.select('INBOX')
        self._check_connection(result)
        self._last_uid = self._get_last_uid(result)

    def _check_connection(self, result):
        if result[0] and result[0] == 'OK':
            return True
        else:
            sys.exit('Connection error')

    def _get_last_uid(self, result=None):
        if not os.path.exists(self.UID_FILE):
            return 1 if result is None else int(result[1][0])
        with open(self.UID_FILE, 'r', encoding='utf-8') as f:
            last_uid = f.read()
        return 1 if not last_uid else last_uid

    def _save_last_uid(self):
        with open(self.UID_FILE, 'w', encoding='utf-8') as f:
            f.write(str(int(self._last_uid)))

    def _get_code_from_email(
        self, email_content: email.message.Message
    ) -> str:
        msg: email.message.Message = email_content
        search_string: str = ''
        for part in msg.walk():
            try:
                search_string += base64.b64decode(part.get_payload()).decode()
            except Exception:
                pass
        try:
            return (
                search_string.split('Ваш код для входа в кабинет Flocktory')[1]
                .split('<b>')[1]
                .split('</b>')[0]
                .strip()
            )
        except Exception:
            return ''

    def check_last_mail(
        self, sleep_interval: int = 5, max_checks: int = 0
    ) -> str:
        code: str = ''
        i: int = 0
        while True:
            i += 1
            if max_checks > 0 and i == max_checks:
                break
            messages = self.imap.uid('search', '1:*')
            code = self._parse_for_code(messages)
            if code:
                break
            sleep(sleep_interval)
        return code

    def _parse_for_code(self, messages) -> str | None:
        try:
            message_list = messages[1][0].split()
        except Exception as e:
            print(e)
            return
        message_list.reverse()

        for message_id in message_list:
            print(message_id)
            result, data = self.imap.uid('fetch', message_id, '(RFC822)')
            email_content = email.message_from_bytes(data[0][1])
            try:
                email_subject = email.header.decode_header(
                    email_content['Subject']
                )[0][0].decode()
            except Exception as e:
                print(e, f'uid: {message_id}')
                email_subject = None
            print('Subject:', email_subject)
            if email_subject and (
                'flocktory authentification code' in email_subject.lower()
            ):
                return self._get_code_from_email(email_content)
