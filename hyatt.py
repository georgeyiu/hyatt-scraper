import datetime
import requests
import shutil
import sys
import urllib

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

SCRAPE_START = '2025-04-20'
SCRAPE_END   = '2025-05-01'
NIGHTS = 2

###############################
###############################


DELAY_SECS = 1
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
}
WAIT_MSG = '[Attention] Cookie expired. Refresh the booking page in Chrome. Script will automatically continue after.'


def make_request(url, checkin_dt, checkout_dt):
    location = url.split('?')[0].split('/')[-1]
    checkin = checkin_dt.strftime('%Y-%m-%d')
    checkout = checkout_dt.strftime('%Y-%m-%d')
    formatted_url = f'https://www.hyatt.com/shop/rates/{location}?checkinDate={checkin}&checkoutDate={checkout}&rooms=1&adults=2&kids=0&rate=Standard&rateFilter=woh'
    response = requests.get(formatted_url, headers=HEADERS)
    print(response.status_code)
    if response.text == '':
        print('empty')
    soup = BeautifulSoup(response.content, 'html.parser')
    tabs = soup.find('div', {'class': 'hbe-header_wohNavTabs'})
    bookings = soup.find_all('div', {'class': 'p-rate-card'})
    availability = []
    results = 0
    for booking in bookings:
        room = booking.find('div', {'class': 'rate-room-title'}).text
        rate = booking.find('div', {'class': 'rate'}).text
        if rate:
            results += 1
        if '$' not in rate:
            availability.append((rate, room))
    dates = '{} - {}: '.format(checkin_dt.strftime('%a %m/%d/%y'), checkout_dt.strftime('%a %m/%d/%y'))
    if not availability:
        if results > 0 or ((soup.findAll('div', {'class': 'Alert_m_booking_alert__uw_Ah'}) or soup.findAll('div', {'class': 'search-hbj'}))):
            # No results were found.
            print(f"{dates}{' '*len(WAIT_MSG)}"[:len(WAIT_MSG)])
        else:
            # Cookie expired.
            # import pdb; pdb.set_trace()
            # print(soup.prettify())
            return False
    else:
        for i, r in enumerate(availability):
            rate_room = f'[{r[0]}] {r[1]}'
            dts = dates if i == 0  else " " * 29
            print(f"{dts}{rate_room}{' '*len(WAIT_MSG)}"[:len(WAIT_MSG)])
    return True


def scrape(scrape_start, scrape_end, nights):
    latest_booking_dt = datetime.datetime.now() + datetime.timedelta(days=394)
    checkin_dt = datetime.datetime.strptime(scrape_start, '%Y-%m-%d')
    end_dt = datetime.datetime.strptime(scrape_end, '%Y-%m-%d')
    hotel_name, url = get_hotel_and_url()
    print(f'{"#"*80}\n{hotel_name}, {nights} nights\n{"#"*80}')
    refresh_cookie()
    while checkin_dt <= end_dt:
        checkout_dt = checkin_dt + datetime.timedelta(days=nights)
        if checkout_dt >= latest_booking_dt:
            print('Bookings are only allowed 13 months in advance. Ending search now.')
            return
        succeeded = False
        failed_count = 0
        while not succeeded:
            succeeded = make_request(url, checkin_dt, checkout_dt)
            if not succeeded:
                if failed_count == 1:
                    print(WAIT_MSG, end='')
                    print('\r', end='')
                failed_count += 1
                refresh_cookie()
                sleep(1)
        checkin_dt = checkin_dt + datetime.timedelta(days=1)


def decrypt_cookie_value(encrypted_value, master_key):
    key = PBKDF2(master_key, b'saltysalt', 16, 1003)
    cipher = AES.new(key, AES.MODE_CBC, IV=b' ' * 16)
    decrypted = cipher.decrypt(encrypted_value[3:])
    return decrypted[:-decrypted[-1]].decode('utf8') if decrypted else ''


def refresh_cookie():
    master_key = Popen(['security', 'find-generic-password', '-w', '-a', 'Chrome', '-s', 'Chrome Safe Storage'], stdout=PIPE).stdout.read().strip()
    shutil.copy(f'{expanduser("~")}/Library/Application Support/Google/Chrome/Profile 2/Cookies', f'{expanduser("~")}/ChromeCookies.tmp')
    with dbapi2.connect(f'{expanduser("~")}/ChromeCookies.tmp') as conn:
        conn.rollback()
        rows1 = conn.cursor().execute('SELECT name, encrypted_value FROM cookies WHERE host_key like ".hyatt.com"')
        rows2 = conn.cursor().execute('SELECT name, encrypted_value FROM cookies WHERE host_key like "www.hyatt.com"')
        # import pdb; pdb.set_trace()
    cookie = ''
    for name, enc_val in rows1:
        val = decrypt_cookie_value(enc_val, master_key)
        if val:
            cookie += f'{name}={val}; '
    for name, enc_val in rows2:
        val = decrypt_cookie_value(enc_val, master_key)
        if val:
            cookie += f'{name}={val}; '
    HEADERS['cookie'] = cookie.strip()


def get_hotel_and_url():
    # shutil.copy(f'{expanduser("~")}/Library/Application Support/Google/Chrome/Default/History', f'{expanduser("~")}/ChromeHistory.tmp')
    # with dbapi2.connect(f'{expanduser("~")}/ChromeHistory.tmp') as conn:
    #     conn.rollback()
    #     rows = conn.cursor().execute(
    #         "SELECT last_visit_time, url FROM urls where url like 'https://www.hyatt.com/shop/%' order by last_visit_time desc")
    # recent, *_ = rows
    # url = recent[1]
    # hotel_name = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['location'][0]
    # return hotel_name, url
    return 'Ventana', 'https://www.hyatt.com/shop/rooms/sjcal?location=Alila+Ventana+Big+Sur&checkinDate=2025-04-22&checkoutDate=2025-04-25&rooms=1&adults=2&kids=0&rate=Standard&rateFilter=woh'


if __name__ == '__main__':
    print(f"Waiting {DELAY_SECS} seconds before starting since Chrome doesn't commit history and cookies to disk instantly...")
    sleep(DELAY_SECS)
    print("If the script isn't looking for the hotel you want, make sure to refresh the page and restart the script.\n")
    print('https://www.hyatt.com/shop/rooms/sjcal?location=Alila%20Ventana%20Big%20Sur&checkinDate=2025-04-20&checkoutDate=2025-04-23&rooms=1&adults=1&kids=0&rate=Standard&rateFilter=woh')
    while True:
        scrape(scrape_start=SCRAPE_START, scrape_end=SCRAPE_END, nights=NIGHTS)
