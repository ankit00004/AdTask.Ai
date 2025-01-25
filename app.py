from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading
import time
import re
from bs4 import BeautifulSoup
import requests
from queue import Queue
import sqlite3
import urllib.parse

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

# Database setup
DB_FILE = "scraped_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            company_name TEXT,
            url TEXT,
            user TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            error_message TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Background scraper
class EmailScraper(threading.Thread):
    def __init__(self):
        super().__init__()
        self.queue = Queue()
        self.scraped_urls = set()
        self.running = True

    def stop(self):
        self.running = False

    def normalize_link(self, link, base_url, page_path):
        if link.startswith('/'):
            return base_url + link
        elif not link.startswith('http'):
            return page_path + link
        return link

    def extract_emails(self, text):
        # Updated email pattern to exclude invalid emails
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = set(re.findall(email_pattern, text, re.I))
        
        # Filter out common invalid patterns or placeholders
        valid_emails = {
            email for email in emails
            if not email.endswith(('example.com', '.png', '.jpg', '.jpeg'))
        }
        return valid_emails

    def get_company_name(self, email_domain):
        common_ignored_names = {"icon", "applynow", "info", "mail", "contact", "support"}
        name = email_domain.split('.')[0]
        if name.lower() in common_ignored_names or len(name) < 3:
            return "Unknown"
        return name.capitalize()

    def save_error(self, url, error_message):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO errors (url, error_message)
            VALUES (?, ?)
        ''', (url, error_message))
        conn.commit()
        conn.close()

        # Emit error to frontend
        socketio.emit('error', {'url': url, 'error_message': error_message})

    def save_data(self, email, company_name, url, user):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO emails (email, company_name, url, user)
            VALUES (?, ?, ?, ?)
        ''', (email, company_name, url, user))
        conn.commit()
        conn.close()

        # Emit new lead to frontend
        socketio.emit('new_lead', {
            'email': email,
            'company_name': company_name,
            'url': url,
            'user': user
        })

    def run(self):
        while self.running:
            try:
                url = self.queue.get(timeout=10)
            except Exception:
                continue

            if url in self.scraped_urls:
                continue

            self.scraped_urls.add(url)
            base_url = urllib.parse.urlsplit(url).scheme + "://" + urllib.parse.urlsplit(url).netloc
            page_path = url[:url.rfind('/') + 1] if '/' in url else url

            try:
                socketio.emit('log', {'message': f'Scraping URL: {url}'})
                response = requests.get(url)
                response.raise_for_status()
                emails = self.extract_emails(response.text)
                soup = BeautifulSoup(response.text, 'lxml')

                for email in emails:
                    domain = email.split('@')[1]
                    user = email.split('@')[0]
                    company_name = self.get_company_name(domain)
                    self.save_data(email, company_name, url, user)

                for anchor in soup.find_all('a'):
                    link = anchor.get('href', '')
                    normalized_link = self.normalize_link(link, base_url, page_path)
                    if normalized_link not in self.scraped_urls:
                        self.queue.put(normalized_link)

            except Exception as e:
                error_message = f"Error processing {url}: {e}"
                print(error_message)
                self.save_error(url, str(e))

scraper = EmailScraper()
scraper.start()

# Flask Routes
@app.route('/')
def index():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT email, company_name, url, user FROM emails ORDER BY id DESC')
    data = cursor.fetchall()
    cursor.execute('SELECT url, error_message FROM errors')
    errors = cursor.fetchall()
    conn.close()
    return render_template('index.html', data=data, errors=errors)

@app.route('/add_url', methods=['POST'])
def add_url():
    url = request.json.get('url')
    scraper.queue.put(url)
    return jsonify({"message": "URL added to the scraping queue."})

@app.route('/stop_scraper', methods=['POST'])
def stop_scraper():
    scraper.stop()
    return jsonify({"message": "Scraper stopped."})

if __name__ == '__main__':
    socketio.run(app, debug=True)
