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
    from telegram import Bot
    from telegram.error import TelegramError
except ImportError:
    import subprocess

    subprocess.check_call(['pip', 'install', 'python-telegram-bot'])
    from telegram import Bot
    from telegram.error import TelegramError

# Configuration
TELEGRAM_BOT_TOKEN = "7111801798:AAF_5EVvMyIUZgISrIqGHT4zRWgTjlWM2L8"  # Get this from BotFather
TELEGRAM_CHAT_ID = "-4836448524"  # Replace with your group's numerical ID (not the URL)
# Increased delay between pages to act more human-like
PAGE_TRANSITION_DELAY = 5  # 5 seconds delay between pages
# Increased delay between course processing
COURSE_PROCESSING_DELAY = 5  # 5 seconds delay between courses
MAX_RETRIES = 3  # Maximum retries for network requests
VERBOSE_DEBUG = True  # Set to True for more detailed debugging
# Telegram sending configurations
TELEGRAM_MAX_RETRIES = 4  # Maximum number of retries for failed messages
TELEGRAM_INITIAL_DELAY = 5  # Initial delay between messages in seconds
TELEGRAM_RATE_LIMIT_DELAY = 60  # Delay in seconds when hitting rate limits


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
        # Get today's date for filtering
        self.today_date = datetime.now().strftime("%B %d, %Y").replace(" 0", " ")  # Format like "May 20, 2025"
        
        # Add debugging info
        if VERBOSE_DEBUG:
            print(f"Initialized scraper with base URL: {base_url}")
            print(f"Today's date for filtering: {self.today_date}")

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
                # Extract publication date
                date_meta = container.find('div', class_='meta post-meta')
                
                # Skip if we can't find date metadata
                if not date_meta:
                    if VERBOSE_DEBUG:
                        print(f"Skipping course {index + 1}: No date metadata found")
                    continue
                
                date_span = date_meta.find('span', class_='date_meta')
                if not date_span:
                    if VERBOSE_DEBUG:
                        print(f"Skipping course {index + 1}: No date span found")
                    continue
                
                publication_date = date_span.text.strip()
                
                # Skip if not today's course
                if publication_date != self.today_date:
                    if VERBOSE_DEBUG:
                        print(f"Skipping course {index + 1}: Not published today (date: {publication_date})")
                    continue
                
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
                        'publication_date': publication_date
                    })

                    if VERBOSE_DEBUG:
                        print(f"Extracted today's course {index + 1}: {title}")
                        print(f"  - URL: {course_url}")
                        print(f"  - Date: {publication_date}")
            except Exception as e:
                if VERBOSE_DEBUG:
                    print(f"Error extracting course {index + 1}: {e}")
                continue

        if VERBOSE_DEBUG:
            print(f"Found {len(courses)} courses published today")
            
        return courses

    def get_udemy_url_from_course_page(self, course_url):
        if VERBOSE_DEBUG:
            print(f"Getting Udemy URL from course page: {course_url}")

        html_content = self.get_page_content(course_url)
        if not html_content:
            if VERBOSE_DEBUG:
                print(f"Failed to get content from course page: {course_url}")
            return None

        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract Udemy link
        coupon_link = soup.find('a', class_='btn_offer_block re_track_btn')

        if coupon_link and 'href' in coupon_link.attrs:
            redirect_url = coupon_link['href']
            redirect_url = redirect_url.replace('&amp;', '&')
            final_url = self.follow_redirect(redirect_url)
            
            # Verify that we got an actual Udemy course URL (not just udemy.com)
            if final_url and 'udemy.com/course/' in final_url:
                if VERBOSE_DEBUG:
                    print(f"Found valid Udemy URL: {final_url}")
                return final_url
            elif final_url and 'udemy.com' in final_url:
                if VERBOSE_DEBUG:
                    print(f"Found invalid Udemy URL (not a specific course): {final_url}")
                return None
            
        if VERBOSE_DEBUG:
            print("No valid Udemy URL found")
        return None

    def follow_redirect(self, url, max_redirects=5):
        if VERBOSE_DEBUG:
            print(f"Following redirect: {url}")

        try:
            response = self.session.get(url, allow_redirects=False, timeout=15)
            redirect_count = 0
            current_url = url

            while redirect_count < max_redirects and (response.status_code in (301, 302, 303, 307, 308)):
                if 'Location' not in response.headers:
                    if VERBOSE_DEBUG:
                        print(f"No Location header found in redirect response")
                    break

                next_url = response.headers['Location']
                if not next_url.startswith('http'):
                    parsed_url = urlparse(current_url)
                    base = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    next_url = urljoin(base, next_url)

                if VERBOSE_DEBUG:
                    print(f"Redirect {redirect_count + 1}: {next_url}")

                current_url = next_url
                response = self.session.get(current_url, allow_redirects=False, timeout=15)
                redirect_count += 1
                time.sleep(0.5)

            # Check if we're still on the couponscorpion site - likely means an error
            if 'couponscorpion.com/recommends' in current_url:
                if VERBOSE_DEBUG:
                    print(f"Still on couponscorpion redirector page - likely an error")
                return None

            # Only consider it successful if we're on a specific Udemy course page
            if 'udemy.com/course/' in current_url:
                return current_url
                
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                meta_refresh = soup.find('meta', attrs={'http-equiv': 'refresh'})
                if meta_refresh and 'content' in meta_refresh.attrs:
                    content = meta_refresh['content']
                    url_match = re.search(r'URL=(.+)', content, re.IGNORECASE)
                    if url_match:
                        refresh_url = url_match.group(1)
                        if 'udemy.com/course/' in refresh_url:
                            if VERBOSE_DEBUG:
                                print(f"Found Udemy course URL in meta refresh: {refresh_url}")
                            return refresh_url

            # Return None if we're just on the main Udemy page, not a specific course
            if current_url == "https://www.udemy.com/":
                return None
                
            return current_url if 'udemy.com/course/' in current_url else None

        except Exception as e:
            if VERBOSE_DEBUG:
                print(f"Error following redirect: {e}")
            return None

    def extract_coupon_code(self, url):
        if not url:
            return None

        coupon_patterns = [
            r'couponCode=([A-Z0-9_]+)',
            r'coupon=([A-Z0-9_]+)',
            r'code=([A-Z0-9_]+)',
            r'promo=([A-Z0-9_]+)',
            r'promocode=([A-Z0-9_]+)'
        ]

        for pattern in coupon_patterns:
            url_match = re.search(pattern, url, re.IGNORECASE)
            if url_match:
                code = url_match.group(1)
                if VERBOSE_DEBUG:
                    print(f"Extracted coupon code: {code} using pattern: {pattern}")
                return code

        if VERBOSE_DEBUG:
            print(f"No coupon code found in URL: {url}")
        return None

    def detect_page_url_format(self, category):
        """Detect the correct URL format for pagination by checking both possible formats"""
        # Try the /category/ format first
        test_url = f"{self.base_url}/category/{category}/page/2/"
        content = self.get_page_content(test_url)
        if content and "<title>Page not found" not in content:
            if VERBOSE_DEBUG:
                print(f"Detected pagination format: /category/{category}/page/N/")
            return "category"

        # Fall back to /{category}/page/ format
        test_url = f"{self.base_url}/{category}/page/2/"
        content = self.get_page_content(test_url)
        if content and "<title>Page not found" not in content:
            if VERBOSE_DEBUG:
                print(f"Detected pagination format: /{category}/page/N/")
            return "direct"

        # If both fail, use the default category page (no pagination)
        if VERBOSE_DEBUG:
            print(f"Could not detect pagination format, using default category page")
        return "none"

    def get_url_for_page(self, category, page_num, url_format):
        """Get the URL for a specific page based on the detected format"""
        if page_num == 1:
            # For first page, we have two possible formats
            if url_format == "category":
                return f"{self.base_url}/category/{category}/"
            else:  # "direct" or "none"
                return f"{self.base_url}/{category}/"
        else:
            # For other pages
            if url_format == "category":
                return f"{self.base_url}/category/{category}/page/{page_num}/"
            elif url_format == "direct":
                return f"{self.base_url}/{category}/page/{page_num}/"
            else:
                # No pagination detected, shouldn't reach here for page > 1
                return f"{self.base_url}/{category}/"

    def scrape_udemy_courses(self, category="personal-development", start_page=1, max_pages=3, verbose=False):
        all_courses = []
        telegram_messages = []
        total_links = 0
        valid_links = 0

        current_date = datetime.now().strftime("%Y-%m-%d")
        summary_message = f"🔥 <b>TODAY'S FREE UDEMY {category.upper()} COURSES</b> - {current_date} 🔥\n\n<i>Finding today's latest free courses for you...</i>"
        telegram_messages.append(summary_message)

        # Detect the correct URL format for this category
        url_format = self.detect_page_url_format(category)
        
        if VERBOSE_DEBUG:
            print(f"Detected URL format: {url_format}")
            print(f"Searching for courses published today: {self.today_date}")

        for page_num in range(start_page, start_page + max_pages):
            if verbose or VERBOSE_DEBUG:
                print(f"Scraping page {page_num} of {category}...")

            # Get the correct URL for this page
            page_url = self.get_url_for_page(category, page_num, url_format)
            
            if VERBOSE_DEBUG:
                print(f"Using URL: {page_url}")

            html_content = self.get_page_content(page_url)
            if not html_content:
                if verbose or VERBOSE_DEBUG:
                    print(f"Failed to fetch page {page_num}, stopping.")
                break

            # Check if returned page is valid (not 404/error page)
            if "<title>Page not found" in html_content:
                if verbose or VERBOSE_DEBUG:
                    print(f"Page {page_num} not found, stopping.")
                break

            courses = self.extract_courses(html_content)
            if not courses:
                if verbose or VERBOSE_DEBUG:
                    print(f"No today's courses found on page {page_num}.")
                # Continue to next page instead of stopping since we're filtering by date
                continue

            if verbose or VERBOSE_DEBUG:
                print(f"Found {len(courses)} today's courses on page {page_num}")

            for i, course in enumerate(courses):
                try:
                    if verbose or VERBOSE_DEBUG:
                        print(f"Processing {i + 1}/{len(courses)}: {course['title']}")

                    # Add a human-like delay between processing each course
                    if i > 0:
                        delay_time = COURSE_PROCESSING_DELAY + random.uniform(-1, 1)  # 4-6 second delay
                        if VERBOSE_DEBUG:
                            print(f"Waiting {delay_time:.1f} seconds before processing next course...")
                        time.sleep(delay_time)

                    udemy_url = self.get_udemy_url_from_course_page(course['url'])

                    if udemy_url:
                        course['udemy_url'] = udemy_url
                        coupon_code = self.extract_coupon_code(udemy_url)
                        course['coupon_code'] = coupon_code

                        all_courses.append(course)
                        total_links += 1
                        valid_links += 1

                        description = course['description']
                        if description:
                            if len(description) > 200:
                                description = description[:197] + "..."
                            description = f"📝 <i>{description}</i>\n\n"

                        coupon_text = f"🎟️ <b>Coupon Code:</b> <code>{coupon_code}</code>\n" if coupon_code else ""

                        message = (
                            f"🔥 <b>{course['title']}</b>\n\n"
                            f"{description}"
                            f"🌐 <a href='{udemy_url}'>Enroll Now (Free)</a>\n"
                            f"{coupon_text}"
                            f"📢 Share with friends who want to learn!\n\n"
                            f"#TodaysFreeCourse #Udemy #{category.capitalize().replace('-', '')} #OnlineLearning #PersonalDevelopment"
                        )

                        telegram_messages.append(message)

                        # Print key information to console
                        print(f"{course['title']} - {udemy_url} {'- Coupon: ' + coupon_code if coupon_code else ''}")
                        print(f"Published: {course['publication_date']}")
                        print("-" * 80)
                    else:
                        print(f"⚠️ Invalid or empty Udemy URL for: {course['title']} - Skipping")
                        print("-" * 80)
                        total_links += 1  # Count it in total but not valid

                except Exception as e:
                    if verbose or VERBOSE_DEBUG:
                        print(f"Error processing course: {e}")
                    continue

            # Human-like delay between pages
            if page_num < start_page + max_pages - 1:
                page_delay = PAGE_TRANSITION_DELAY + random.uniform(-1, 2)  # 4-7 second delay
                if VERBOSE_DEBUG:
                    print(f"\nWaiting {page_delay:.1f} seconds before moving to page {page_num + 1}...\n")
                time.sleep(page_delay)

        if verbose or VERBOSE_DEBUG:
            print(f"Total today's Udemy links processed: {total_links}")
            print(f"Valid today's Udemy links found: {valid_links}")
            print(f"Invalid/empty links: {total_links - valid_links}")

        if valid_links > 0:
            summary = f"✅ <b>Today's Free {category.capitalize().replace('-', ' ')} Courses Update</b>\n\nJust shared {valid_links} free Udemy courses published TODAY ({self.today_date})! Grab them while they last.\n\n#TodaysUdemy #FreshCourses #{category.capitalize().replace('-', '')} #PersonalDevelopment"
            telegram_messages.append(summary)
        else:
            summary = f"ℹ️ <b>No New {category.capitalize().replace('-', ' ')} Courses Today</b>\n\nNo new free Udemy courses found for today ({self.today_date}). Check back later!\n\n#UdemyUpdate #{category.capitalize().replace('-', '')} #PersonalDevelopment"
            telegram_messages.append(summary)

        return all_courses, telegram_messages

    def save_results(self, courses, json_filename="udemy_courses.json", csv_filename="udemy_courses.csv"):
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(courses, f, indent=2, ensure_ascii=False)

        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            csv_writer = csv.writer(f)
            header = ['Title', 'Description', 'Udemy URL', 'Coupon Code', 'Publication Date']
            csv_writer.writerow(header)

            for course in courses:
                row = [
                    course['title'],
                    course['description'],
                    course.get('udemy_url', 'N/A'),
                    course.get('coupon_code', 'N/A'),
                    course.get('publication_date', 'N/A')
                ]
                csv_writer.writerow(row)


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
            # Increase timeouts to prevent timeouts on longer messages
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0
        )
        if VERBOSE_DEBUG:
            print(f"Successfully sent message to Telegram")
        return True
    except TelegramError as e:
        # Handle rate limiting or timeout errors
        if "Too Many Requests" in str(e) or "Timed out" in str(e):
            # Increase wait time exponentially with each retry
            wait_time = 5 * (2 ** retry_count)
            if retry_count < max_retries:
                if VERBOSE_DEBUG:
                    print(
                        f"Telegram rate limit/timeout hit. Retrying in {wait_time} seconds... ({retry_count + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
                return await send_to_telegram_group(message, bot_token, chat_id, retry_count + 1, max_retries)
            else:
                if VERBOSE_DEBUG:
                    print(f"Failed after {max_retries} attempts: {e}")
        else:
            if VERBOSE_DEBUG:
                print(f"Error sending to Telegram: {e}")
        return False
    except Exception as e:
        if VERBOSE_DEBUG:
            print(f"Unexpected error sending to Telegram: {e}")
        return False


async def run_telegram_operations(messages, bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID):
    connection_ok = await test_telegram_connection(bot_token, chat_id)
    if not connection_ok:
        print("Telegram connection failed. Skipping message sending.")
        return

    print(f"Starting to send {len(messages)} messages to Telegram (with improved rate limiting)...")
    success_count = 0
    failure_count = 0
    failed_messages = []

    # Initial message sending with human-like randomized delays
    for idx, msg in enumerate(messages, 1):
        print(f"Sending message {idx}/{len(messages)}...")
        success = await send_to_telegram_group(msg, bot_token, chat_id)
        if success:
            success_count += 1
            # Human-like randomized delay between messages
            delay = random.uniform(5.0, 8.0)
            await asyncio.sleep(delay)
        else:
            failure_count += 1
            failed_messages.append(msg)
            # Wait longer after a failure before continuing
            await asyncio.sleep(random.uniform(10.0, 15.0))

    # Retry failed messages with higher delays
    if failed_messages:
        print(f"\nRetrying {len(failed_messages)} failed messages with increased delays...")
        retry_success = 0

        for idx, msg in enumerate(failed_messages, 1):
            print(f"Retry attempt for message {idx}/{len(failed_messages)}...")
            # Use a longer maximum wait time for retries
            success = await send_to_telegram_group(msg, bot_token, chat_id, max_retries=4)
            if success:
                retry_success += 1
                success_count += 1
                failure_count -= 1
                # Even longer delay between retry attempts
                await asyncio.sleep(random.uniform(12.0, 18.0))
            else:
                # Wait substantially longer after a failed retry
                await asyncio.sleep(random.uniform(15.0, 20.0))

        print(f"Retry results: {retry_success}/{len(failed_messages)} messages recovered")

    print(f"\nFinal results - Messages sent: {success_count}, Failed: {failure_count}")

    if failure_count > 0:
        print("Note: For the failed messages, you can try running the script again later "
              "when Telegram's rate limits have reset.")


def get_chat_id(chat_id_input):
    if chat_id_input.startswith('-100'):
        return chat_id_input
    if chat_id_input.startswith('https://t.me/'):
        username = chat_id_input.split('/')[-1]
        return username
    if chat_id_input.startswith('@'):
        return chat_id_input
    return chat_id_input


async def main():
    print("Starting Improved Udemy Coupon Scraper - PERSONAL DEVELOPMENT (ALL COURSES)")
    print("============================================================================")
    print(f"Current date: {datetime.now().strftime('%B %d, %Y')}")
    print("============================================================================")

    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN" or TELEGRAM_CHAT_ID == "YOUR_GROUP_ID":
        print("ERROR: Please set your Telegram bot token and group ID in the script!")
        return

    chat_id = get_chat_id(TELEGRAM_CHAT_ID)
    scraper = UdemyCouponScraper()

    # CHANGED: Updated category to "personal-development"
    category = "personal-development"

    # Scraping 6 pages as requested
    max_pages = 6
    print(f"\nScraping the '{category}' category for {max_pages} pages (ALL COURSES, not just today)...")
    print(f"Using human-like delays: {PAGE_TRANSITION_DELAY} seconds between pages, {COURSE_PROCESSING_DELAY} seconds between courses")
    print("============================================================================")

    courses, telegram_messages = scraper.scrape_udemy_courses(
        category=category,
        max_pages=max_pages,
        verbose=True  # More verbose output
    )

    valid_courses = [c for c in courses if 'udemy_url' in c and c['udemy_url'] and 'udemy.com/course/' in c['udemy_url']]
    
    if valid_courses:
        json_file = f"udemy_courses_{category}_all.json"
        csv_file = f"udemy_courses_{category}_all.csv"
        scraper.save_results(valid_courses, json_filename=json_file, csv_filename=csv_file)
        print(f"\nSaved {len(valid_courses)} valid course data to {json_file} and {csv_file}")
    else:
        print("\nNo valid courses found to save")

    # Send messages to Telegram
    if telegram_messages:
        print(f"\nSending {len(telegram_messages)} messages to Telegram...")
        await run_telegram_operations(telegram_messages, TELEGRAM_BOT_TOKEN, chat_id)
        print("Completed sending messages to Telegram!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
