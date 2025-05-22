import requests
from bs4 import BeautifulSoup
import json
import time
import random
import csv
import os
import re
import asyncio
from urllib.parse import urljoin, urlparse
from datetime import datetime

# Telegram imports
try:
    from telegram import Bot, Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters
    from telegram.error import TelegramError
except ImportError:
    import subprocess

    subprocess.check_call(['pip', 'install', 'python-telegram-bot'])
    from telegram import Bot, Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters
    from telegram.error import TelegramError

# Configuration
TELEGRAM_BOT_TOKEN = "7833928371:AAFcWWJ8XBT7Z_GXcKw7wTrPWqdDRemcEHs"
TELEGRAM_CHAT_ID = "2132787978"
DELAY_SECONDS = 1
MAX_RETRIES = 3
VERBOSE_DEBUG = True

# Category mappings for user requests
CATEGORY_MAPPING = {
    'ui': 'design',
    'ux': 'design',
    'design': 'design',
    'app': 'mobile',
    'mobile': 'mobile',
    'android': 'mobile',
    'ios': 'mobile',
    'web': 'development',
    'development': 'development',
    'dev': 'development',
    'programming': 'development',
    'code': 'development',
    'marketing': 'marketing',
    'business': 'business',
    'photography': 'photography',
    'music': 'music',
    'lifestyle': 'lifestyle',
    'health': 'health',
    'fitness': 'health',
    'categories': 'help'  # Special case to show categories
}


class UdemyCouponScraper:
    def __init__(self, base_url="https://couponscorpion.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': base_url
        })

        # Cache for storing daily courses by category
        self.daily_courses_cache = {}
        self.cache_date = None

        if VERBOSE_DEBUG:
            print(f"Initialized scraper with base URL: {base_url}")

    def get_page_content(self, url, max_retries=3):
        if VERBOSE_DEBUG:
            print(f"Fetching page: {url}")

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=15, allow_redirects=True)
                response.raise_for_status()
                if VERBOSE_DEBUG:
                    print(f"Successfully fetched page: {url} (size: {len(response.text)} bytes)")
                return response.text
            except requests.exceptions.RequestException as e:
                wait_time = 2 ** attempt
                if VERBOSE_DEBUG:
                    print(f"Error fetching page (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(wait_time)

        if VERBOSE_DEBUG:
            print(f"Failed to fetch page after {max_retries} attempts: {url}")
        return None

    def extract_courses(self, html_content):
        courses = []
        soup = BeautifulSoup(html_content, 'html.parser')
        course_containers = soup.find_all('div', class_='news-community clearfix')

        if VERBOSE_DEBUG:
            print(f"Found {len(course_containers)} course containers")

        for index, container in enumerate(course_containers):
            try:
                title_element = container.find('h2').find('a')
                if not title_element:
                    continue

                title = title_element.text.strip()
                course_url = title_element['href']

                description_element = container.find('p', class_=lambda x: x and ('font90' in x or 'mobfont80' in x))
                description = description_element.text.strip() if description_element else "No description available"

                if title and course_url:
                    if not course_url.startswith('http'):
                        course_url = urljoin(self.base_url, course_url)

                    courses.append({
                        'title': title,
                        'url': course_url,
                        'description': description,
                    })

                    if VERBOSE_DEBUG:
                        print(f"Extracted course {index + 1}: {title}")
            except Exception as e:
                if VERBOSE_DEBUG:
                    print(f"Error extracting course {index + 1}: {e}")
                continue

        return courses

    def get_udemy_url_from_course_page(self, course_url):
        if VERBOSE_DEBUG:
            print(f"Getting Udemy URL from course page: {course_url}")

        html_content = self.get_page_content(course_url)
        if not html_content:
            return None

        soup = BeautifulSoup(html_content, 'html.parser')
        coupon_link = soup.find('a', class_='btn_offer_block re_track_btn')

        if coupon_link and 'href' in coupon_link.attrs:
            redirect_url = coupon_link['href']
            redirect_url = redirect_url.replace('&amp;', '&')
            final_url = self.follow_redirect(redirect_url)
            return final_url

        return None

    def follow_redirect(self, url, max_redirects=5):
        try:
            response = self.session.get(url, allow_redirects=False, timeout=15)
            redirect_count = 0
            current_url = url

            while redirect_count < max_redirects and (response.status_code in (301, 302, 303, 307, 308)):
                if 'Location' not in response.headers:
                    break

                next_url = response.headers['Location']
                if not next_url.startswith('http'):
                    parsed_url = urlparse(current_url)
                    base = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    next_url = urljoin(base, next_url)

                current_url = next_url
                response = self.session.get(current_url, allow_redirects=False, timeout=15)
                redirect_count += 1
                time.sleep(0.5)

            if 'udemy.com' in current_url:
                return current_url

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                meta_refresh = soup.find('meta', attrs={'http-equiv': 'refresh'})
                if meta_refresh and 'content' in meta_refresh.attrs:
                    content = meta_refresh['content']
                    url_match = re.search(r'URL=(.+)', content, re.IGNORECASE)
                    if url_match:
                        refresh_url = url_match.group(1)
                        if 'udemy.com' in refresh_url:
                            return refresh_url

            return current_url if 'udemy.com' in current_url else None

        except Exception as e:
            if VERBOSE_DEBUG:
                print(f"Error following redirect: {e}")
            return None

    def extract_coupon_code(self, url):
        if not url:
            return None

        coupon_patterns = [
            r'couponCode=([A-Z0-9]+)',
            r'coupon=([A-Z0-9]+)',
            r'code=([A-Z0-9]+)',
            r'promo=([A-Z0-9]+)',
            r'promocode=([A-Z0-9]+)'
        ]

        for pattern in coupon_patterns:
            url_match = re.search(pattern, url, re.IGNORECASE)
            if url_match:
                code = url_match.group(1)
                return code

        return None

    def detect_page_url_format(self, category):
        test_url = f"{self.base_url}/category/{category}/page/2/"
        content = self.get_page_content(test_url)
        if content and "<title>Page not found" not in content:
            return "category"

        test_url = f"{self.base_url}/{category}/page/2/"
        content = self.get_page_content(test_url)
        if content and "<title>Page not found" not in content:
            return "direct"

        return "none"

    def scrape_category_courses(self, category, max_pages=2):
        """Scrape courses for a specific category"""
        courses = []

        # Check if we have cached data for today
        today = datetime.now().strftime("%Y-%m-%d")
        if self.cache_date == today and category in self.daily_courses_cache:
            return self.daily_courses_cache[category]

        url_format = self.detect_page_url_format(category)

        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                page_url = f"{self.base_url}/{category}/"
            else:
                if url_format == "category":
                    page_url = f"{self.base_url}/category/{category}/page/{page_num}/"
                elif url_format == "direct":
                    page_url = f"{self.base_url}/{category}/page/{page_num}/"
                else:
                    break

            html_content = self.get_page_content(page_url)
            if not html_content or "<title>Page not found" in html_content:
                break

            page_courses = self.extract_courses(html_content)
            if not page_courses:
                break

            for course in page_courses:
                udemy_url = self.get_udemy_url_from_course_page(course['url'])
                if udemy_url:
                    course['udemy_url'] = udemy_url
                    course['coupon_code'] = self.extract_coupon_code(udemy_url)
                    courses.append(course)

                time.sleep(random.uniform(0.5, 1))

        # Cache the results
        if self.cache_date != today:
            self.daily_courses_cache = {}
            self.cache_date = today

        self.daily_courses_cache[category] = courses
        return courses

    def scrape_udemy_courses(self, category="development", start_page=1, max_pages=3, verbose=False):
        all_courses = []
        telegram_messages = []
        total_links = 0

        current_date = datetime.now().strftime("%Y-%m-%d")
        summary_message = f"🔥 <b>FREE UDEMY {category.upper()} COURSES</b> - {current_date} 🔥\n\n<i>Finding the latest free courses for you...</i>"
        telegram_messages.append(summary_message)

        url_format = self.detect_page_url_format(category)

        for page_num in range(start_page, start_page + max_pages):
            if verbose or VERBOSE_DEBUG:
                print(f"Scraping page {page_num} of {category}...")

            if page_num == 1:
                page_url = f"{self.base_url}/{category}/"
            else:
                if url_format == "category":
                    page_url = f"{self.base_url}/category/{category}/page/{page_num}/"
                elif url_format == "direct":
                    page_url = f"{self.base_url}/{category}/page/{page_num}/"
                else:
                    if page_num > 1:
                        break
                    page_url = f"{self.base_url}/{category}/"

            html_content = self.get_page_content(page_url)
            if not html_content or "<title>Page not found" in html_content:
                break

            courses = self.extract_courses(html_content)
            if not courses:
                break

            for i, course in enumerate(courses):
                try:
                    udemy_url = self.get_udemy_url_from_course_page(course['url'])

                    if udemy_url:
                        course['udemy_url'] = udemy_url
                        coupon_code = self.extract_coupon_code(udemy_url)
                        course['coupon_code'] = coupon_code

                        all_courses.append(course)
                        total_links += 1

                        description = course['description']
                        if description and len(description) > 200:
                            description = description[:197] + "..."

                        desc_text = f"📝 <i>{description}</i>\n\n" if description else ""
                        coupon_text = f"🎟️ <b>Coupon Code:</b> <code>{coupon_code}</code>\n" if coupon_code else ""

                        message = (
                            f"🔥 <b>{course['title']}</b>\n\n"
                            f"{desc_text}"
                            f"🌐 <a href='{udemy_url}'>Enroll Now (Free)</a>\n"
                            f"{coupon_text}"
                            f"📢 Share with friends who want to learn!\n\n"
                            f"#FreeCourse #Udemy #{category.capitalize()} #OnlineLearning"
                        )

                        telegram_messages.append(message)
                        print(f"{course['title']} - {udemy_url}")
                        print("-" * 80)

                except Exception as e:
                    if verbose or VERBOSE_DEBUG:
                        print(f"Error processing course: {e}")
                    continue

                time.sleep(random.uniform(0.5, 1))

        if total_links > 0:
            summary = f"✅ <b>Today's Free {category.capitalize()} Courses Update</b>\n\nJust shared {total_links} free Udemy courses! Grab them while they last.\n\n#FreeUdemy #CourseUpdate #{category.capitalize()}"
            telegram_messages.append(summary)

        return all_courses, telegram_messages

    def save_results(self, courses, json_filename="udemy_courses.json", csv_filename="udemy_courses.csv"):
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(courses, f, indent=2, ensure_ascii=False)

        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            csv_writer = csv.writer(f)
            header = ['Title', 'Description', 'Udemy URL', 'Coupon Code']
            csv_writer.writerow(header)

            for course in courses:
                row = [
                    course['title'],
                    course['description'],
                    course.get('udemy_url', 'N/A'),
                    course.get('coupon_code', 'N/A')
                ]
                csv_writer.writerow(row)


# Global scraper instance
scraper = UdemyCouponScraper()


async def start_command(update: Update, context):
    """Handle /start command"""
    welcome_message = """
🤖 <b>Welcome to Free Udemy Courses Bot!</b>

I can help you find today's free Udemy courses in different categories.

<b>Available commands:</b>
• Type <code>ui</code> or <code>design</code> - Get UI/UX Design courses
• Type <code>app</code> or <code>mobile</code> - Get Mobile App Development courses  
• Type <code>web</code> or <code>development</code> - Get Web Development courses
• Type <code>marketing</code> - Get Marketing courses
• Type <code>business</code> - Get Business courses
• Type <code>photography</code> - Get Photography courses

Just send me any of these keywords and I'll fetch today's free courses for you! 🚀

<i>Note: This bot works in private messages only.</i>
"""

    await update.message.reply_text(welcome_message, parse_mode='HTML')


async def help_command(update: Update, context):
    """Handle /help command"""
    help_message = """
<b>🔥 Free Udemy Courses Bot - Help</b>

<b>How to use:</b>
1. Send me a category keyword (like 'ui', 'web', 'app')
2. I'll fetch today's free courses for that category
3. Click on the course links to enroll for free!

<b>Available categories:</b>
• <code>/ui</code> or <code>ui</code> → UI/UX Design courses
• <code>/app</code> or <code>app</code> → Mobile Development
• <code>/web</code> or <code>web</code> → Web Development
• <code>/marketing</code> or <code>marketing</code> → Digital Marketing courses
• <code>/business</code> or <code>business</code> → Business & Entrepreneurship
• <code>/photography</code> or <code>photography</code> → Photography courses

<b>Commands:</b>
• <code>/categories</code> - Show detailed category list
• <code>/help</code> - Show this help message

<b>Examples:</b>
- Send "/ui" or "ui" to get design courses
- Send "/web" or "web" to get web development courses
- Send "/app" or "app" to get mobile development courses

💡 <i>Tip: Courses are updated daily, so check back regularly!</i>
"""

    await update.message.reply_text(help_message, parse_mode='HTML')


async def categories_command(update: Update, context):
    """Handle /categories command"""
    categories_message = """
📚 <b>Available Course Categories:</b>

🎨 <b>Design & UI/UX:</b>
• <code>/ui</code> or <code>ui</code> - UI/UX Design courses
• <code>/design</code> or <code>design</code> - General design courses

📱 <b>Mobile Development:</b>
• <code>/app</code> or <code>app</code> - Mobile app development
• <code>/mobile</code> or <code>mobile</code> - Mobile development

💻 <b>Web Development:</b>
• <code>/web</code> or <code>web</code> - Web development courses
• <code>/development</code> or <code>development</code> - Programming courses

📈 <b>Business & Marketing:</b>
• <code>/marketing</code> or <code>marketing</code> - Digital marketing
• <code>/business</code> or <code>business</code> - Business & entrepreneurship

📸 <b>Creative:</b>
• <code>/photography</code> or <code>photography</code> - Photography courses

<b>💡 How to use:</b>
Just send me any category keyword (with or without /) and I'll fetch today's free courses!

<i>Example: Send "ui" or "/ui" to get design courses</i>
"""

    await update.message.reply_text(categories_message, parse_mode='HTML')


async def handle_category_request(update: Update, context):
    """Handle category requests from users"""
    user_message = update.message.text.lower().strip()
    chat_type = update.effective_chat.type

    # Only respond to private messages
    if chat_type != 'private':
        return

    # Remove leading slash if present (for command-style requests)
    if user_message.startswith('/'):
        user_message = user_message[1:]

    # Check if the message matches any category
    if user_message == 'categories':
        await categories_command(update, context)
        return

    category = CATEGORY_MAPPING.get(user_message)

    if not category:
        # If not a recognized category, show help
        await update.message.reply_text(
            "🤔 I didn't understand that category. Use /help to see available categories.",
            parse_mode='HTML'
        )
        return

    # Show loading message
    loading_msg = await update.message.reply_text(
        f"🔍 <b>Searching for today's free {category} courses...</b>\n\n<i>This might take a moment...</i>",
        parse_mode='HTML'
    )

    try:
        # Scrape courses for the requested category
        courses = scraper.scrape_category_courses(category, max_pages=2)

        if not courses:
            await loading_msg.edit_text(
                f"😔 <b>No free {category} courses found today.</b>\n\nTry checking back later or try another category!",
                parse_mode='HTML'
            )
            return

        # Delete loading message
        await loading_msg.delete()

        # Send header message
        current_date = datetime.now().strftime("%Y-%m-%d")
        header_msg = f"🔥 <b>FREE {category.upper()} COURSES TODAY</b> - {current_date}\n\n<i>Found {len(courses)} free courses for you!</i>"
        await update.message.reply_text(header_msg, parse_mode='HTML')

        # Send course messages (limit to 10 courses to avoid spam)
        for i, course in enumerate(courses[:10]):
            description = course['description']
            if description and len(description) > 150:
                description = description[:147] + "..."

            desc_text = f"📝 <i>{description}</i>\n\n" if description else ""
            coupon_text = f"🎟️ <b>Coupon:</b> <code>{course['coupon_code']}</code>\n" if course.get(
                'coupon_code') else ""

            message = (
                f"🎓 <b>{course['title']}</b>\n\n"
                f"{desc_text}"
                f"🌐 <a href='{course['udemy_url']}'>Enroll Now (Free)</a>\n"
                f"{coupon_text}"
                f"#{category.capitalize()}Course #{i + 1}"
            )

            await update.message.reply_text(message, parse_mode='HTML', disable_web_page_preview=True)

            # Small delay to avoid rate limiting
            await asyncio.sleep(1)

        # Send summary
        if len(courses) > 10:
            summary_msg = f"📊 <b>Summary:</b> Showed top 10 out of {len(courses)} available courses.\n\n💡 <i>Come back tomorrow for fresh courses!</i>"
        else:
            summary_msg = f"✅ <b>That's all for today's {category} courses!</b>\n\n💡 <i>Come back tomorrow for fresh courses!</i>"

        await update.message.reply_text(summary_msg, parse_mode='HTML')

    except Exception as e:
        await loading_msg.edit_text(
            f"❌ <b>Error fetching courses:</b>\n<i>{str(e)}</i>\n\nPlease try again later.",
            parse_mode='HTML'
        )
        print(f"Error in handle_category_request: {e}")


async def test_telegram_connection(bot_token, chat_id):
    try:
        bot = Bot(token=bot_token)
        test_message = f"🧪 Testing Telegram connection - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        await bot.send_message(
            chat_id=chat_id,
            text=test_message,
            parse_mode='HTML',
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0
        )
        print("✅ Telegram connection successful!")
        return True
    except Exception as e:
        print(f"❌ Telegram connection test failed: {e}")
        return False


async def send_to_telegram_group(message, bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID, retry_count=0,
                                 max_retries=3):
    try:
        bot = Bot(token=bot_token)
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='HTML',
            disable_web_page_preview=False,
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0
        )
        return True
    except TelegramError as e:
        if "Too Many Requests" in str(e) or "Timed out" in str(e):
            wait_time = 5 * (2 ** retry_count)
            if retry_count < max_retries:
                await asyncio.sleep(wait_time)
                return await send_to_telegram_group(message, bot_token, chat_id, retry_count + 1, max_retries)
        return False
    except Exception as e:
        print(f"Unexpected error sending to Telegram: {e}")
        return False


async def run_telegram_operations(messages, bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID):
    connection_ok = await test_telegram_connection(bot_token, chat_id)
    if not connection_ok:
        print("Telegram connection failed. Skipping message sending.")
        return

    print(f"Starting to send {len(messages)} messages to Telegram...")
    success_count = 0
    failure_count = 0

    for idx, msg in enumerate(messages, 1):
        print(f"Sending message {idx}/{len(messages)}...")
        success = await send_to_telegram_group(msg, bot_token, chat_id)
        if success:
            success_count += 1
            await asyncio.sleep(random.uniform(3.0, 5.0))
        else:
            failure_count += 1
            await asyncio.sleep(random.uniform(6.0, 10.0))

    print(f"\nFinal results - Messages sent: {success_count}, Failed: {failure_count}")


def get_chat_id(chat_id_input):
    if chat_id_input.startswith('-100'):
        return chat_id_input
    if chat_id_input.startswith('https://t.me/'):
        username = chat_id_input.split('/')[-1]
        return username
    if chat_id_input.startswith('@'):
        return chat_id_input
    return chat_id_input


async def run_bot_webhook():
    """Run the bot to listen for private messages"""
    print("Starting Telegram Bot for private message handling...")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("categories", categories_command))

    # Add command handlers for each category
    for category_key in CATEGORY_MAPPING.keys():
        if category_key not in ['categories']:  # Skip special cases
            application.add_handler(CommandHandler(category_key, handle_category_request))

    # Handle text messages (non-command style)
    application.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, handle_category_request))

    # Start the bot
    await application.initialize()
    await application.start()

    print("✅ Bot is running and listening for messages...")

    # Keep the bot running
    try:
        await application.updater.start_polling()
        # Keep running until interrupted
        import signal
        stop_event = asyncio.Event()

        def signal_handler():
            stop_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda s, f: signal_handler())

        await stop_event.wait()

    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


async def scheduled_scraping():
    """Run the scheduled scraping for the group (for GitHub Actions)"""
    print("Starting Udemy Coupon Scraper (Scheduled Mode)")

    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN" or TELEGRAM_CHAT_ID == "YOUR_GROUP_ID":
        print("ERROR: Please set your Telegram bot token and group ID in the script!")
        return

    chat_id = get_chat_id(TELEGRAM_CHAT_ID)

    category = "development"
    max_pages = 1
    print(f"\nScraping the '{category}' category for {max_pages} pages...")

    courses, telegram_messages = scraper.scrape_udemy_courses(
        category=category,
        max_pages=max_pages,
        verbose=True
    )

    if courses:
        json_file = f"udemy_courses_{category}.json"
        csv_file = f"udemy_courses_{category}.csv"
        scraper.save_results(courses, json_filename=json_file, csv_filename=csv_file)
        print(f"Saved course data to {json_file} and {csv_file}")

    if telegram_messages:
        print(f"Sending {len(telegram_messages)} messages to Telegram...")
        await run_telegram_operations(telegram_messages, TELEGRAM_BOT_TOKEN, chat_id)
        print("Completed sending messages to Telegram!")


async def main():
    """Main function - determines whether to run as bot or scheduled scraper"""
    import sys

    # Check if running in bot mode or scheduled mode
    if len(sys.argv) > 1 and sys.argv[1] == "bot":
        # Run as interactive bot
        await run_bot_webhook()
    else:
        # Run as scheduled scraper (default for GitHub Actions)
        await scheduled_scraping()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
