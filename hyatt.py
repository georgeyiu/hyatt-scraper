import datetime
import requests
import shutil
import sys
import time
import urllib
from pprint import pprint as pp

from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from os.path import expanduser
from sqlite3 import dbapi2
from subprocess import PIPE, Popen
from time import sleep

"""
INSTRUCTIONS:

Install dependencies as needed. This script is meant to run under Python 3. Python 2 might work but is untested.

pip install beautifulsoup4
pip install pycrypto

1. In Google Chrome, visit any booking results page of the hotel you're interested in. The dates and availability don't matter.
   Example: https://www.hyatt.com/shop/sjcjc?checkinDate=2025-04-20&checkoutDate=2025-04-23&rooms=1&adults=2&kids=0&rate=Standard&rateFilter=woh

2. Edit the SCRAPE_START, SCRAPE_END, and NIGHTS variables as needed (just below these instructions).

3. Run the script: "python hyatt.py"

4. If the "Cookie expired" prompt appears, refresh the booking page in Chrome. 
   The script should continue automatically (usually in 15 to 30 seconds, max 1 min).
"""

###############################
###############################

SCRAPE_START = '2024-04-20'
SCRAPE_END   = '2025-05-01'
NIGHTS = 2

###############################
###############################


DELAY_SECS = 1
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'en-US,en;q=0.9',
    'Dnt': '1',
    'Sec-Ch-Ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"macOS"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
}
WAIT_MSG = '[Attention] Cookie expired. Refresh the booking page in Chrome. Script will automatically continue after.'


def make_request(checkin_dt, checkout_dt):
    location = 'Ventana' #url.split('?')[0].split('/')[-1]
    checkin = checkin_dt.strftime('%Y-%m-%d')
    checkout = checkout_dt.strftime('%Y-%m-%d')
    formatted_url = f'https://www.hyatt.com/shop/service/rooms/roomrates/sjcal?spiritCode=sjcal&rooms=1&adults=1&location=Alila%20Ventana%20Big%20Sur&checkinDate={checkin}&checkoutDate={checkout}&kids=0&rate=Standard&rateFilter=woh'
    response = requests.get(formatted_url, headers=HEADERS)
    if response.status_code != 200:
        # print(f'failed to fetch {formatted_url}')
        return False
    if response.text == '':
        # print(f'empty response {formatted_url}')
        return False
    availability = []
    data = response.json()
    for _, info in data['roomRates'].items():
        rate = info['lowestAvgPointValue']
        if rate == None:
            continue
        rate = (str(rate)[::-1].replace('000', 'k'))[::-1]
        room = info['roomType']['title']
        availability.append((rate, room))
    dates = '{} - {}: '.format(checkin_dt.strftime('%a %m/%d/%y'), checkout_dt.strftime('%a %m/%d/%y'))
    for i, r in enumerate(availability):
        rate_room = f'[{r[0]}] {r[1]}'
        dts = dates if i == 0  else " " * 29
        print(f"{dts}{rate_room}{' '*len(WAIT_MSG)}"[:len(WAIT_MSG)])
    if not availability:
        print(f"{dates}{' '*len(WAIT_MSG)}"[:len(WAIT_MSG)])
    return True


def scrape(scrape_start, scrape_end, nights):
    latest_booking_dt = datetime.datetime.now() + datetime.timedelta(days=394)
    checkin_dt = datetime.datetime.strptime(scrape_start, '%Y-%m-%d')
    end_dt = datetime.datetime.strptime(scrape_end, '%Y-%m-%d')
    print(f'{"#"*80}\nVentana, {nights} nights\n{"#"*80}')
    while checkin_dt <= end_dt:
        checkout_dt = checkin_dt + datetime.timedelta(days=nights)
        if checkout_dt >= latest_booking_dt:
            print('Bookings are only allowed 13 months in advance. Ending search now.')
            return
        succeeded = False
        failed_count = 0
        while not succeeded:
            succeeded = make_request(checkin_dt, checkout_dt)
            if not succeeded:
                if failed_count == 1:
                    print(WAIT_MSG, end='')
                    print('\r', end='')
                failed_count += 1
                clear_cookie()
                fetch_cookie()
                sleep(5)
        checkin_dt = checkin_dt + datetime.timedelta(days=1)


def decrypt_cookie_value(encrypted_value, master_key):
    key = PBKDF2(master_key, b'saltysalt', 16, 1003)
    cipher = AES.new(key, AES.MODE_CBC, IV=b' ' * 16)
    decrypted = cipher.decrypt(encrypted_value[3:])
    return decrypted[:-decrypted[-1]].decode('utf8') if decrypted else ''


def clear_cookie():
    with dbapi2.connect(f'{expanduser("~")}/ChromeCookies.tmp') as conn:
        conn.rollback()
        rows1 = conn.cursor().execute('DELETE FROM cookies WHERE host_key like ".hyatt.com"')
        rows2 = conn.cursor().execute('DELETE FROM cookies WHERE host_key like "www.hyatt.com"')


def fetch_cookie():
    master_key = Popen(['security', 'find-generic-password', '-w', '-a', 'Chrome', '-s', 'Chrome Safe Storage'], stdout=PIPE).stdout.read().strip()
    shutil.copy(f'{expanduser("~")}/Library/Application Support/Google/Chrome/Default/Cookies', f'{expanduser("~")}/ChromeCookies.tmp')
    with dbapi2.connect(f'{expanduser("~")}/ChromeCookies.tmp') as conn:
        conn.rollback()
        rows1 = conn.cursor().execute('SELECT name, encrypted_value FROM cookies WHERE host_key like ".hyatt.com"')
        rows2 = conn.cursor().execute('SELECT name, encrypted_value FROM cookies WHERE host_key like "www.hyatt.com"')
    cookie = ''
    for name, enc_val in rows1:
        val = decrypt_cookie_value(enc_val, master_key)
        if val:
            if name == 'utag_main_ses_id':
                val = str(int(time.time()) * 100) + val[13:]
                print(f'===================== {val}')
            cookie += f'{name}={val}; '
    for name, enc_val in rows2:
        val = decrypt_cookie_value(enc_val, master_key)
        if val:
            if name == 'utag_main_ses_id':
                val = str(int(time.time()) * 100 + 10000) + val[13:]
                print(f'===================== {val}')
            cookie += f'{name}={val}; '
    old = HEADERS.get('cookie', '')
    if not cookie:
        return('')
    HEADERS['cookie'] = cookie.strip()
    old_d = set([x.strip() for x in old.split(';')])
    print(f'old: {[str(z) for z in old_d]}')
    print('new:')
    for a in cookie.split(';'):
        if a.strip() not in old_d:
            print(a)
    return(cookie)


if __name__ == '__main__':
    print(f"Waiting {DELAY_SECS} seconds before starting since Chrome doesn't commit history and cookies to disk instantly...")
    sleep(DELAY_SECS)
    print("https://www.google.com/search?q=hyatt&sca_esv=98cc110fba7c9a23&sxsrf=ACQVn08M5E9GcXlaopTGBLoa8Wbm6T-qlw%3A1713060399178&ei=LzobZrm4CpvKp84Pm86R6A8&ved=0ahUKEwj5i8mkz8CFAxUb5ckDHRtnBP0Q4dUDCBE&uact=5&oq=hyatt&gs_lp=Egxnd3Mtd2l6LXNlcnAiBWh5YXR0MgQQABhHMgQQABhHMgQQABhHMgQQABhHMgQQABhHMgQQABhHMgQQABhHMgQQABhHSKoEULMBWLMBcAF4ApABAJgBAKABAKoBALgBA8gBAPgBAZgCAqACB8ICBxAjGLADGCfCAgoQABhHGNYEGLADwgINEAAYRxjWBBjJAxiwA8ICDhAAGIAEGIoFGJIDGLADwgIOEAAY5AIY1gQYsAPYAQHCAhkQLhiABBiKBRhDGMcBGNEDGMgDGLAD2AECwgIXEC4YgAQY5wQYxwEY0QMYyAMYsAPYAQKYAwDiAwUSATEgQIgGAZAGCLoGBggBEAEYCboGBggCEAEYCJIHATKgBwA&sclient=gws-wiz-serp")
    print("chrome://settings/content/all?searchSubpage=hyatt")
    while True:
        scrape(scrape_start=SCRAPE_START, scrape_end=SCRAPE_END, nights=NIGHTS)
