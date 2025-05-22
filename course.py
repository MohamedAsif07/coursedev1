import requests, json, time, random, asyncio, os, re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "7833928371:AAFcWWJ8XBT7Z_GXcKw7wTrPWqdDRemcEHs")
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', "2132787978")
GITHUB_TOKEN = "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"
GITHUB_REPO = 'MohamedAsif07/coursedev1'

CATEGORIES = {'ui': 'design', 'app': 'mobile', 'web': 'development', 'marketing': 'marketing', 'business': 'business',
              'photography': 'photography'}


class UdemyScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        self.base_url = "https://couponscorpion.com"

    def get_page(self, url):
        try:
            return self.session.get(url, timeout=15).text
        except:
            return None

    def extract_courses(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        courses = []
        for container in soup.find_all('div', class_='news-community clearfix'):
            try:
                title_elem = container.find('h2').find('a')
                title = title_elem.text.strip()
                url = title_elem['href']
                if not url.startswith('http'):
                    url = urljoin(self.base_url, url)
                desc_elem = container.find('p', class_=lambda x: x and 'font90' in x)
                desc = desc_elem.text.strip() if desc_elem else ""
                courses.append({'title': title, 'url': url, 'description': desc})
            except:
                continue
        return courses

    def get_udemy_url(self, course_url):
        html = self.get_page(course_url)
        if not html:
            return None
        soup = BeautifulSoup(html, 'html.parser')
        link = soup.find('a', class_='btn_offer_block re_track_btn')
        if link and 'href' in link.attrs:
            redirect_url = link['href'].replace('&amp;', '&')
            return self.follow_redirects(redirect_url)
        return None

    def follow_redirects(self, url):
        try:
            for _ in range(5):
                response = self.session.get(url, allow_redirects=False, timeout=15)
                if response.status_code in (301, 302, 303, 307, 308):
                    url = response.headers.get('Location', url)
                else:
                    break
                time.sleep(0.5)
            return url if 'udemy.com' in url else None
        except:
            return None

    def extract_coupon(self, url):
        if not url:
            return None
        patterns = [r'couponCode=([A-Z0-9]+)', r'coupon=([A-Z0-9]+)', r'code=([A-Z0-9]+)']
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def scrape_category(self, category):
        courses = []
        page_url = f"{self.base_url}/{category}/"
        html = self.get_page(page_url)
        if not html:
            return courses

        page_courses = self.extract_courses(html)
        for course in page_courses[:8]:
            udemy_url = self.get_udemy_url(course['url'])
            if udemy_url:
                course['udemy_url'] = udemy_url
                course['coupon_code'] = self.extract_coupon(udemy_url)
                courses.append(course)
            time.sleep(1)
        return courses


scraper = UdemyScraper()


async def trigger_github_action(category, user_id):
    if not GITHUB_TOKEN:
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.everest-preview+json'
    }
    data = {
        'event_type': 'user_request',
        'client_payload': {
            'category': category,
            'user_id': str(user_id),
            'timestamp': datetime.now().isoformat()
        }
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 204
    except:
        return False


async def start_command(update: Update, context):
    message = """🤖 <b>Free Udemy Courses Bot</b>

Created by <b>Mohamed Asif</b> - App Developer & Cybersecurity Enthusiast
🌐 https://asifappdev.tech/

<b>Commands:</b>
• <code>/ui</code> - UI/UX Design courses
• <code>/web</code> - Web Development courses
• <code>/app</code> - Mobile App courses
• <code>/marketing</code> - Marketing courses
• <code>/business</code> - Business courses
• <code>/photography</code> - Photography courses

<i>Private messages only</i>"""
    await update.message.reply_text(message, parse_mode='HTML')


async def category_handler(update: Update, context):
    if update.effective_chat.type != 'private':
        await update.message.reply_text("🔒 Private messages only", parse_mode='HTML')
        return

    command = update.message.text.lower().strip().replace('/', '')
    category = CATEGORIES.get(command)

    if not category:
        await update.message.reply_text("❌ Unknown category. Use /start for help.", parse_mode='HTML')
        return

    user_id = update.effective_user.id
    loading_msg = await update.message.reply_text(f"🔍 <b>Getting {category} courses...</b>", parse_mode='HTML')

    if os.getenv('GITHUB_ACTIONS'):
        courses = scraper.scrape_category(category)
        await send_courses_to_user(update, courses, category, user_id)
    else:
        triggered = await trigger_github_action(category, user_id)
        if triggered:
            await loading_msg.edit_text(f"⚡ Processing your {category} request...\nCourses will be sent shortly!",
                                        parse_mode='HTML')
        else:
            courses = scraper.scrape_category(category)
            await send_courses_to_user(update, courses, category, user_id)

    await loading_msg.delete()


async def send_courses_to_user(update, courses, category, user_id):
    if not courses:
        await update.message.reply_text(f"😔 No {category} courses found today.", parse_mode='HTML')
        return

    date = datetime.now().strftime("%Y-%m-%d")
    header = f"🔥 <b>{category.upper()} COURSES - {date}</b>\nFound {len(courses)} courses!"
    await update.message.reply_text(header, parse_mode='HTML')

    for i, course in enumerate(courses[:6], 1):
        desc = course['description'][:100] + "..." if len(course['description']) > 100 else course['description']
        coupon = f"🎟️ <code>{course['coupon_code']}</code>\n" if course.get('coupon_code') else ""

        msg = f"🎓 <b>{course['title']}</b>\n\n📝 {desc}\n\n🌐 <a href='{course['udemy_url']}'>Enroll Free</a>\n{coupon}#{category} #{i}"
        await update.message.reply_text(msg, parse_mode='HTML', disable_web_page_preview=True)
        await asyncio.sleep(1)


async def process_github_webhook():
    payload = json.loads(os.getenv('GITHUB_EVENT_PAYLOAD', '{}'))
    if payload.get('action') == 'user_request':
        client_payload = payload.get('client_payload', {})
        category = client_payload.get('category')
        user_id = client_payload.get('user_id')

        if category and user_id:
            courses = scraper.scrape_category(category)
            await send_courses_directly(user_id, courses, category)


async def send_courses_directly(user_id, courses, category):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    if not courses:
        await bot.send_message(chat_id=user_id, text=f"😔 No {category} courses found today.", parse_mode='HTML')
        return

    date = datetime.now().strftime("%Y-%m-%d")
    header = f"🔥 <b>{category.upper()} COURSES - {date}</b>\nFound {len(courses)} courses!"
    await bot.send_message(chat_id=user_id, text=header, parse_mode='HTML')

    for i, course in enumerate(courses[:6], 1):
        desc = course['description'][:100] + "..." if len(course['description']) > 100 else course['description']
        coupon = f"🎟️ <code>{course['coupon_code']}</code>\n" if course.get('coupon_code') else ""

        msg = f"🎓 <b>{course['title']}</b>\n\n📝 {desc}\n\n🌐 <a href='{course['udemy_url']}'>Enroll Free</a>\n{coupon}#{category} #{i}"
        await bot.send_message(chat_id=user_id, text=msg, parse_mode='HTML', disable_web_page_preview=True)
        await asyncio.sleep(1)


async def scheduled_group_post():
    courses = scraper.scrape_category('development')
    if courses:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        date = datetime.now().strftime("%Y-%m-%d")
        header = f"🔥 <b>DAILY FREE COURSES - {date}</b>\n{len(courses)} Development courses!"
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=header, parse_mode='HTML')

        for course in courses[:5]:
            desc = course['description'][:120] + "..." if len(course['description']) > 120 else course['description']
            coupon = f"🎟️ <code>{course['coupon_code']}</code>\n" if course.get('coupon_code') else ""

            msg = f"🎓 <b>{course['title']}</b>\n\n📝 {desc}\n\n🌐 <a href='{course['udemy_url']}'>Enroll Free</a>\n{coupon}#FreeCourse"
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='HTML')
            await asyncio.sleep(2)


async def main():
    import sys

    if os.getenv('GITHUB_EVENT_NAME') == 'repository_dispatch':
        await process_github_webhook()
    elif len(sys.argv) > 1 and sys.argv[1] == "bot":
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start_command))
        for cat in CATEGORIES.keys():
            app.add_handler(CommandHandler(cat, category_handler))
        app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, category_handler))

        await app.initialize()
        await app.start()
        print("✅ Bot running...")
        await app.updater.start_polling()

        import signal
        stop = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda s, f: stop.set())
        await stop.wait()

        await app.updater.stop()
        await app.stop()
        await app.shutdown()
    else:
        await scheduled_group_post()


if __name__ == "__main__":
    asyncio.run(main())
