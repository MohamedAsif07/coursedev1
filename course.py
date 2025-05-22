import requests, json, time, random, asyncio, os, re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
PERSONAL_ACCESS_TOKEN = os.getenv('PERSONAL_ACCESS_TOKEN')
REPO_NAME = os.getenv('REPO_NAME', 'MohamedAsif07/coursedev1')

CATEGORIES = {
    'ui': 'design', 
    'app': 'mobile', 
    'web': 'development', 
    'marketing': 'marketing', 
    'business': 'business',
    'photography': 'photography'
}

class UdemyScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.base_url = "https://couponscorpion.com"

    def get_page(self, url):
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def extract_courses(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        courses = []
        
        selectors = [
            'div.news-community.clearfix',
            'article.post',
            'div.course-item',
            'div.coupon-card'
        ]
        
        for selector in selectors:
            containers = soup.select(selector)
            if containers:
                break
        
        for container in containers[:10]:
            try:
                title_elem = container.find('h2') or container.find('h3') or container.find('h4')
                if not title_elem:
                    continue
                    
                title_link = title_elem.find('a')
                if not title_link:
                    continue
                    
                title = title_link.get_text(strip=True)
                url = title_link.get('href', '')
                
                if not url.startswith('http'):
                    url = urljoin(self.base_url, url)
                
                desc_elem = container.find('p') or container.find('div', class_='excerpt')
                desc = desc_elem.get_text(strip=True)[:200] if desc_elem else "Free Udemy Course"
                
                if title and url:
                    courses.append({
                        'title': title,
                        'url': url,
                        'description': desc
                    })
            except Exception as e:
                print(f"Error extracting course: {e}")
                continue
        
        return courses

    def get_udemy_url(self, course_url):
        try:
            html = self.get_page(course_url)
            if not html:
                return None
                
            soup = BeautifulSoup(html, 'html.parser')
            
            selectors = [
                'a.btn_offer_block',
                'a[href*="udemy.com"]',
                'a.coupon-btn',
                'a.btn-primary'
            ]
            
            for selector in selectors:
                link = soup.select_one(selector)
                if link and link.get('href'):
                    redirect_url = link['href'].replace('&amp;', '&')
                    final_url = self.follow_redirects(redirect_url)
                    if final_url and 'udemy.com' in final_url:
                        return final_url
            
            return None
        except Exception as e:
            print(f"Error getting Udemy URL: {e}")
            return None

    def follow_redirects(self, url, max_redirects=5):
        try:
            for i in range(max_redirects):
                response = self.session.get(url, allow_redirects=False, timeout=10)
                
                if response.status_code in [200, 404]:
                    return url
                elif response.status_code in [301, 302, 303, 307, 308]:
                    location = response.headers.get('Location')
                    if not location:
                        break
                    if not location.startswith('http'):
                        location = urljoin(url, location)
                    url = location
                    time.sleep(0.3)
                else:
                    break
            
            return url if 'udemy.com' in url else None
        except Exception as e:
            print(f"Error following redirects: {e}")
            return None

    def extract_coupon(self, url):
        if not url:
            return None
        patterns = [
            r'couponCode=([A-Z0-9]+)',
            r'coupon=([A-Z0-9]+)', 
            r'code=([A-Z0-9]+)',
            r'/([A-Z0-9]{6,})/?(?:\?|$)'
        ]
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def scrape_category(self, category):
        print(f"Scraping {category} courses...")
        courses = []
        
        urls_to_try = [
            f"{self.base_url}/category/{category}/",
            f"{self.base_url}/{category}/",
            f"{self.base_url}/courses/{category}/",
            f"{self.base_url}"
        ]
        
        for page_url in urls_to_try:
            html = self.get_page(page_url)
            if html:
                page_courses = self.extract_courses(html)
                if page_courses:
                    break
        
        if not page_courses:
            print(f"No courses found for {category}")
            return []
        
        for course in page_courses[:6]:
            try:
                udemy_url = self.get_udemy_url(course['url'])
                if udemy_url:
                    course['udemy_url'] = udemy_url
                    course['coupon_code'] = self.extract_coupon(udemy_url)
                    courses.append(course)
                    print(f"✓ Found: {course['title'][:50]}...")
                time.sleep(random.uniform(1, 2))
            except Exception as e:
                print(f"Error processing course: {e}")
                continue
        
        return courses

scraper = UdemyScraper()

async def trigger_github_action(category, user_id):
    if not PERSONAL_ACCESS_TOKEN or not REPO_NAME:
        print("Personal access token or repo not configured")
        return False

    url = f"https://api.github.com/repos/{REPO_NAME}/dispatches"
    headers = {
        'Authorization': f'token {PERSONAL_ACCESS_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
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
        response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"GitHub API response: {response.status_code}")
        return response.status_code == 204
    except Exception as e:
        print(f"Error triggering GitHub action: {e}")
        return False

async def start_command(update: Update, context):
    message = """🤖 <b>Free Udemy Courses Bot</b>

Created by <b>Mohamed Asif</b> - App Developer
🌐 Portfolio: https://asifappdev.tech/

<b>Available Commands:</b>
• /ui - UI/UX Design courses
• /web - Web Development courses  
• /app - Mobile App courses
• /marketing - Marketing courses
• /business - Business courses
• /photography - Photography courses

<i>⚠️ Use in private chat only</i>"""
    
    await update.message.reply_text(message, parse_mode='HTML')

async def category_handler(update: Update, context):
    if update.effective_chat.type != 'private':
        await update.message.reply_text(
            "🔒 <b>Private Messages Only</b>\n\nPlease message me privately to get courses.",
            parse_mode='HTML'
        )
        return

    command = update.message.text.lower().strip().replace('/', '')
    category = CATEGORIES.get(command)

    if not category:
        await update.message.reply_text(
            "❌ <b>Unknown Command</b>\n\nUse /start to see available categories.",
            parse_mode='HTML'
        )
        return

    user_id = update.effective_user.id
    
    loading_msg = await update.message.reply_text(
        f"🔍 <b>Searching for {category} courses...</b>\n⏳ Please wait...",
        parse_mode='HTML'
    )

    try:
        if os.getenv('ACTIONS_RUNNER') == 'true':
            courses = scraper.scrape_category(category)
            await send_courses_to_user(update, courses, category)
        else:
            triggered = await trigger_github_action(category, user_id)
            if triggered:
                await loading_msg.edit_text(
                    f"⚡ <b>Processing Request</b>\n\n🔄 Scraping {category} courses...\n📤 Results will be sent shortly!",
                    parse_mode='HTML'
                )
                return
            else:
                await loading_msg.edit_text(
                    f"🔄 <b>Fallback Mode</b>\n\nScraping courses directly...",
                    parse_mode='HTML'
                )
                courses = scraper.scrape_category(category)
                await send_courses_to_user(update, courses, category)
        
        await loading_msg.delete()
        
    except Exception as e:
        print(f"Error in category handler: {e}")
        await loading_msg.edit_text("❌ Something went wrong. Please try again later.")

async def send_courses_to_user(update, courses, category):
    if not courses:
        await update.message.reply_text(
            f"😔 <b>No {category} courses found</b>\n\nTry again later or check other categories.",
            parse_mode='HTML'
        )
        return

    date = datetime.now().strftime("%B %d, %Y")
    header = f"🔥 <b>{category.upper()} COURSES</b>\n📅 {date}\n\n✅ Found {len(courses)} free courses!"
    
    await update.message.reply_text(header, parse_mode='HTML')

    for i, course in enumerate(courses, 1):
        try:
            title = course['title'][:80] + "..." if len(course['title']) > 80 else course['title']
            desc = course['description'][:150] + "..." if len(course['description']) > 150 else course['description']
            
            coupon_text = ""
            if course.get('coupon_code'):
                coupon_text = f"\n🎟️ Coupon: <code>{course['coupon_code']}</code>"

            msg = f"""🎓 <b>{title}</b>

📝 {desc}

🌐 <a href='{course['udemy_url']}'>Enroll Free Now</a>{coupon_text}

#{category} #FreeCourse #{i}"""

            await update.message.reply_text(
                msg, 
                parse_mode='HTML', 
                disable_web_page_preview=True
            )
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Error sending course {i}: {e}")
            continue

async def process_github_webhook():
    try:
        payload = json.loads(os.getenv('EVENT_PAYLOAD', '{}'))
        client_payload = payload.get('client_payload', {})
        category = client_payload.get('category')
        user_id = client_payload.get('user_id')

        if category and user_id:
            print(f"Processing webhook request: {category} for user {user_id}")
            courses = scraper.scrape_category(category)
            await send_courses_directly(user_id, courses, category)
        else:
            print("Invalid webhook payload")
    except Exception as e:
        print(f"Error processing webhook: {e}")

async def send_courses_directly(user_id, courses, category):
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)

        if not courses:
            await bot.send_message(
                chat_id=user_id,
                text=f"😔 <b>No {category} courses found</b>\n\nTry again later or check other categories.",
                parse_mode='HTML'
            )
            return

        date = datetime.now().strftime("%B %d, %Y")
        header = f"🔥 <b>{category.upper()} COURSES</b>\n📅 {date}\n\n✅ Found {len(courses)} free courses!"
        
        await bot.send_message(chat_id=user_id, text=header, parse_mode='HTML')

        for i, course in enumerate(courses, 1):
            try:
                title = course['title'][:80] + "..." if len(course['title']) > 80 else course['title']
                desc = course['description'][:150] + "..." if len(course['description']) > 150 else course['description']
                
                coupon_text = ""
                if course.get('coupon_code'):
                    coupon_text = f"\n🎟️ Coupon: <code>{course['coupon_code']}</code>"

                msg = f"""🎓 <b>{title}</b>

📝 {desc}

🌐 <a href='{course['udemy_url']}'>Enroll Free Now</a>{coupon_text}

#{category} #FreeCourse #{i}"""

                await bot.send_message(
                    chat_id=user_id,
                    text=msg,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Error sending course {i}: {e}")
                continue
                
    except Exception as e:
        print(f"Error sending courses directly: {e}")

async def scheduled_group_post():
    try:
        courses = scraper.scrape_category('development')
        if not courses:
            print("No courses found for daily post")
            return

        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        date = datetime.now().strftime("%B %d, %Y")
        
        header = f"""🔥 <b>DAILY FREE COURSES</b>
📅 {date}

🎓 {len(courses)} Development courses available!

Created by Mohamed Asif - App Developer
🌐 https://asifappdev.tech/"""

        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=header, parse_mode='HTML')

        for i, course in enumerate(courses[:5], 1):
            try:
                title = course['title'][:70] + "..." if len(course['title']) > 70 else course['title']
                desc = course['description'][:120] + "..." if len(course['description']) > 120 else course['description']
                
                coupon_text = ""
                if course.get('coupon_code'):
                    coupon_text = f"\n🎟️ <code>{course['coupon_code']}</code>"

                msg = f"""🎓 <b>{title}</b>

📝 {desc}

🌐 <a href='{course['udemy_url']}'>Enroll Free</a>{coupon_text}

#FreeCourse #Daily #{i}"""

                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=msg,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                await asyncio.sleep(2)
            except Exception as e:
                print(f"Error in daily post {i}: {e}")
                continue
                
    except Exception as e:
        print(f"Error in scheduled post: {e}")

async def main():
    import sys
    
    print("Starting application...")

    if os.getenv('EVENT_NAME') == 'repository_dispatch':
        print("Processing GitHub webhook...")
        await process_github_webhook()
    elif len(sys.argv) > 1 and sys.argv[1] == "bot":
        print("Starting bot in interactive mode...")
        
        if not TELEGRAM_BOT_TOKEN:
            print("❌ TELEGRAM_BOT_TOKEN not found!")
            return
            
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", start_command))
        
        for cat in CATEGORIES.keys():
            app.add_handler(CommandHandler(cat, category_handler))
        
        app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, category_handler))

        await app.initialize()
        await app.start()
        print("✅ Bot is running and ready!")
        
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
        print("Running scheduled group post...")
        await scheduled_group_post()

if __name__ == "__main__":
    asyncio.run(main())
