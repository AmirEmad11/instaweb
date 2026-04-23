"""
وحدة محرك الأتمتة (Automation Engine)
تحتوي على منطق المتابعة وإرسال الرسائل والرد على التعليقات
تدعم الحسابات العامة والخاصة
"""

import asyncio
import logging
import random

from playwright.async_api import Page
from config import (
    MESSAGE_TEMPLATES,
    COMMENT_REPLY_TEXT,
    DELAY_MIN_MESSAGE,
    DELAY_MAX_MESSAGE,
)
from utils import (
    random_delay,
    get_random_message,
    human_like_click,
    human_like_mouse_move,
    take_error_screenshot,
)

logger = logging.getLogger(__name__)

BUTTON_TIMEOUT_MS = 1000  # ثانية واحدة فقط - Turbo Mode


class AutomationEngine:
    """
    محرك الأتمتة - يتولى المتابعة والرسائل والردود
    يدعم الحسابات العامة والخاصة مع إمكانية الرد التلقائي على الخاصة
    """

    def __init__(self, page: Page):
        self.page = page
        self.message_templates = MESSAGE_TEMPLATES
        self.comment_reply_text = COMMENT_REPLY_TEXT
        self.private_auto_reply = False
        self.private_reply_text = "تم إرسال التفاصيل، يرجى مراجعة طلبات المراسلة ✅"

    # ─────────────────────────────────────────────────────────────
    #  فحص نوع الحساب
    # ─────────────────────────────────────────────────────────────

    async def _check_if_private(self) -> bool:
        """كشف الحساب الخاص فوري بدون انتظار"""
        try:
            # فحص سريع بـ JavaScript - بدون انتظار DOM
            is_priv = await self.page.evaluate("""
                () => {
                    const body = document.body?.innerText || document.body?.textContent || '';
                    const html = document.documentElement?.innerHTML || '';
                    const indicators = [
                        '"is_private":true', 'isPrivate":true',
                        'This Account is Private', 'هذا الحساب خاص',
                        'private account'
                    ];
                    return indicators.some(k => html.toLowerCase().includes(k.toLowerCase())
                                              || body.toLowerCase().includes(k.toLowerCase()));
                }
            """)
            if is_priv:
                return True
            # فحص ثانوي سريع: وجود زر Restricted أو غياب Posts
            el = await self.page.query_selector(
                'span:text-matches("Private|خاص|Restricted", "i")'
            )
            return el is not None
        except Exception:
            return False

    async def _find_visible_locator(self, selectors: list[str], timeout: int = BUTTON_TIMEOUT_MS):
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                await locator.wait_for(state="visible", timeout=timeout)
                return locator
            except Exception:
                continue
        return None

    async def _click_follow_button(self, username: str) -> bool:
        """الضغط على زر المتابعة بطريقة بشرية"""
        follow_selectors = [
            "xpath=//button[contains(normalize-space(.), 'Follow') and not(contains(normalize-space(.), 'Following')) and not(contains(normalize-space(.), 'Unfollow'))]",
            "xpath=//button[contains(normalize-space(.), 'متابعة')]",
            "xpath=//*[@role='button' and contains(normalize-space(.), 'Follow') and not(contains(normalize-space(.), 'Following')) and not(contains(normalize-space(.), 'Unfollow'))]",
            "xpath=//*[@role='button' and contains(normalize-space(.), 'متابعة')]",
            'button[aria-label*="Follow"]',
            'button[aria-label*="متابعة"]',
            '[role="button"][aria-label*="Follow"]',
            '[role="button"][aria-label*="متابعة"]',
        ]
        button = await self._find_visible_locator(follow_selectors)
        if not button:
            return False

        try:
            text = (await button.inner_text(timeout=BUTTON_TIMEOUT_MS)).strip().lower()
        except Exception:
            text = ""

        if "following" in text or "unfollow" in text or "يتابع" in text:
            logger.info(f"@{username} متابَع بالفعل")
            return False

        await human_like_mouse_move(
            self.page,
            400 + (hash(username) % 100),
            300 + (hash(username) % 50),
        )
        await random_delay(0.3, 0.8)
        await button.click(timeout=BUTTON_TIMEOUT_MS)
        await random_delay(0.8, 1.5)
        return True

    # ─────────────────────────────────────────────────────────────
    #  زيارة البروفايل والمتابعة
    # ─────────────────────────────────────────────────────────────

    async def visit_and_follow_profile(self, username: str) -> dict:
        """زيارة بروفايل المستخدم والمتابعة - Turbo Mode"""
        result = {"followed": False, "account_type": "unknown"}
        try:
            profile_url = f"https://www.instagram.com/{username}/"
            await self.page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
            await random_delay(1.0, 1.8)

            is_private = await self._check_if_private()
            result["account_type"] = "private" if is_private else "public"

            followed = await self._click_follow_button(username)
            result["followed"] = followed

            if followed:
                if is_private:
                    logger.info(f"[🔒] متابعة (خاص): @{username}")
                else:
                    logger.info(f"[👤] متابعة: @{username}")

        except Exception as e:
            logger.error(f"❌ زيارة @{username}: {e}")

        return result

    # ─────────────────────────────────────────────────────────────
    #  إرسال رسالة DM
    # ─────────────────────────────────────────────────────────────

    async def send_direct_message(self, username: str, user_id: str = None) -> bool:
        """إرسال DM عبر رابط Direct السريع عند توفره"""
        try:
            opened = False
            if user_id:
                direct_url = f"https://www.instagram.com/direct/t/{user_id}/"
                await self.page.goto(direct_url, wait_until="domcontentloaded", timeout=15000)
                await random_delay(3, 8)
                opened = True
            else:
                opened = await self._open_direct_by_username(username)

            if not opened:
                logger.info(f"[⏭] تخطي @{username} - تعذر فتح المحادثة")
                return False

            await self.page.wait_for_selector(
                'div[role="textbox"], textarea[placeholder*="Message"], p[aria-placeholder]',
                timeout=5000,
            )

            message_text = get_random_message(self.message_templates)
            await self._fast_fill_message(message_text)
            await asyncio.sleep(0.5)
            await self.page.keyboard.press("Enter")
            await random_delay(3, 8)

            logger.info(f"📨 رسالة لـ @{username} | الحالة: ناجح")
            return True

        except Exception as e:
            logger.error(f"❌ DM @{username}: {str(e)[:60]}")
            return False

    # ─────────────────────────────────────────────────────────────
    #  الكتابة البشرية
    # ─────────────────────────────────────────────────────────────

    async def _open_direct_by_username(self, username: str) -> bool:
        try:
            await self.page.goto("https://www.instagram.com/direct/new/", wait_until="domcontentloaded", timeout=15000)
            await random_delay(3, 8)

            search_selectors = [
                'input[name="queryBox"]',
                'input[placeholder*="Search"]',
                'input[placeholder*="بحث"]',
                'input[aria-label*="Search"]',
                'input[aria-label*="بحث"]',
                'div[role="textbox"]',
            ]
            search_box = await self._find_visible_locator(search_selectors, timeout=3000)
            if not search_box:
                return False

            await search_box.fill(username)
            await random_delay(3, 8)

            user_option = await self._find_visible_locator(
                [
                    f'xpath=//span[contains(normalize-space(.), "{username}")]',
                    f'xpath=//*[contains(normalize-space(.), "{username}") and (@role="button" or ancestor::*[@role="button"])]',
                ],
                timeout=5000,
            )
            if not user_option:
                return False

            await user_option.click(timeout=BUTTON_TIMEOUT_MS)
            await random_delay(3, 8)

            chat_button = await self._find_visible_locator(
                [
                    'xpath=//div[@role="button" and contains(normalize-space(.), "Chat")]',
                    'xpath=//div[@role="button" and contains(normalize-space(.), "دردشة")]',
                    'xpath=//button[contains(normalize-space(.), "Chat")]',
                    'xpath=//button[contains(normalize-space(.), "دردشة")]',
                ],
                timeout=5000,
            )
            if chat_button:
                await chat_button.click(timeout=BUTTON_TIMEOUT_MS)
                await random_delay(3, 8)
            return True
        except Exception as e:
            logger.error(f"❌ فتح Direct @{username}: {str(e)[:60]}")
            return False

    async def _fast_fill_message(self, text: str):
        """لصق الرسالة فوراً داخل صندوق الكتابة"""
        textbox_selectors = [
            'div[role="textbox"]',
            'textarea[placeholder*="Message"]',
            'p[aria-placeholder]',
        ]
        for selector in textbox_selectors:
            textbox = await self.page.query_selector(selector)
            if textbox and await textbox.is_visible():
                await textbox.click()
                try:
                    await textbox.fill(text)
                    return
                except Exception:
                    await textbox.evaluate(
                        """(element, value) => {
                            element.focus();
                            document.execCommand('selectAll', false, null);
                            document.execCommand('insertText', false, value);
                            element.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
                        }""",
                        text,
                    )
                    return

        await self.page.keyboard.insert_text(text)

    # ─────────────────────────────────────────────────────────────
    #  الرد على التعليقات
    # ─────────────────────────────────────────────────────────────

    async def reply_to_comment(self, post_url: str, username: str,
                               custom_text: str = None) -> bool:
        """
        الرد على تعليق المستخدم في المنشور.
        custom_text: نص مخصص للرد (يُستخدم للحسابات الخاصة)
        """
        reply_text = custom_text or self.comment_reply_text
        try:
            logger.info(f"جارٍ الرد على تعليق @{username} في المنشور")

            await self.page.goto(post_url, wait_until="domcontentloaded")
            await random_delay(3, 8)

            comment_found = await self._find_and_click_reply_on_comment(username)

            if not comment_found:
                logger.warning(f"لم يُعثر على تعليق @{username} للرد عليه")
                return False

            await self._fast_fill_message(reply_text)
            await asyncio.sleep(0.5)
            await self.page.keyboard.press("Enter")
            await random_delay(3, 8)

            logger.info(f"✅ تم الرد على تعليق @{username} بنجاح")
            return True

        except Exception as e:
            logger.error(f"خطأ أثناء الرد على تعليق @{username}: {e}")
            await take_error_screenshot(self.page, f"reply_error_{username}")
            return False

    async def _find_and_click_reply_on_comment(self, username: str) -> bool:
        """البحث عن تعليق المستخدم بالـ aria-labels والـ roles"""
        try:
            result = await self.page.evaluate(f"""
                () => {{
                    const username = "{username}";
                    // البحث بالرابط المرتبط باسم المستخدم
                    const links = document.querySelectorAll('a[href="/' + username + '/"]');
                    for (const link of links) {{
                        // الحاوية: li أو أقرب div
                        const container = link.closest('li') ||
                                          link.closest('[role="row"]') ||
                                          link.closest('div');
                        if (!container) continue;

                        // البحث عن زر الرد بـ aria-label أو نص
                        const replySelectors = [
                            'button[aria-label*="Reply"]',
                            'button[aria-label*="رد"]',
                            'button:has-text("Reply")',
                            'span[role="button"]:has-text("Reply")',
                            'span[role="button"]:has-text("رد")',
                        ];
                        for (const sel of replySelectors) {{
                            const btn = container.querySelector(sel);
                            if (btn) {{
                                btn.click();
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }}
            """)
            if result:
                await random_delay(1, 2)
                return True
            return False
        except Exception as e:
            logger.error(f"خطأ في البحث عن تعليق @{username}: {e}")
            return False

    # ─────────────────────────────────────────────────────────────
    #  ضبط الإعدادات
    # ─────────────────────────────────────────────────────────────

    def set_message_templates(self, templates: list):
        self.message_templates = templates
        logger.info(f"تم تحديث قوالب الرسائل ({len(templates)} قالب)")

    def set_comment_reply_text(self, text: str):
        self.comment_reply_text = text

    def set_private_auto_reply(self, enabled: bool, text: str = None):
        """تفعيل/إلغاء الرد التلقائي على الحسابات الخاصة"""
        self.private_auto_reply = enabled
        if text:
            self.private_reply_text = text
        logger.info(f"الرد التلقائي على الخاصة: {'مفعّل' if enabled else 'معطّل'}")
