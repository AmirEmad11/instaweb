"""
وحدة استخراج العملاء المحتملين (Lead Scraper)
- تستهدف قائمة التعليقات (ul) تحديداً وتستبعد صاحب المنشور
- تستخدم Roles/Aria-labels بدلاً من الـ classes المتغيرة
- وضع Debug: لقطة شاشة + إحصاء العناصر
- يطبع نص التعليق بوضوح في الـ Logs
"""

import asyncio
import logging
import random
import re
from pathlib import Path

from playwright.async_api import Page
import config as cfg
from utils import random_delay, take_error_screenshot

logger = logging.getLogger(__name__)

_HAS_LETTER = re.compile(
    r'[a-zA-Z\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0621-\u064A]'
)


class LeadScraper:

    def __init__(self, page: Page):
        self.page = page
        self.keywords = cfg.KEYWORDS
        self.target_new_comments = 500

    # ─────────────────────────────────────────────────────────────
    #  الدالة الرئيسية
    # ─────────────────────────────────────────────────────────────

    async def scrape_leads_from_post(self, post_url: str) -> list[dict]:
        leads = []
        try:
            logger.info(f"🔍 انتقال إلى المنشور...")
            await self.page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)

            # ① التحقق من تسجيل الدخول
            if not await self._verify_logged_in():
                logger.error("❌ صفحة تسجيل الدخول مكتشفة! التوقف فوراً.")
                await take_error_screenshot(self.page, "login_required")
                return leads

            # ② فتح قسم التعليقات والتمرير
            is_reel = "/reel" in post_url
            if is_reel:
                comments_ready = await self._force_open_reels_comments()
                if not comments_ready:
                    logger.error("❌ لم يتم فتح نافذة تعليقات Reels - لن يبدأ السحب بدون ظهور dialog")
                    await self._take_debug_screenshot("reels_error")
                    return leads
            else:
                await self._open_comments_section()
                await self._wait_for_comments_content()
            scrolls, comment_count = await self._scroll_to_load_comments()
            logger.info(f"[⚡] تحميل {comment_count} تعليق في {scrolls} تمريرة")

            # ③ فتح الردود المخفية بسرعة
            await self._click_view_replies()

            # ④ استخراج العملاء (JavaScript دفعة واحدة)
            leads = await self._extract_leads_from_comments(post_url)
            if not leads:
                logger.info("🔁 لم تظهر تعليقات بعد - محاولة Scroll إضافية للتحقق قبل الخروج")
                await self._extra_scroll_for_comments()
                await asyncio.sleep(1)
                await self._click_view_replies()
                leads = await self._extract_leads_from_comments(post_url)
                if not leads:
                    await self._take_debug_screenshot("reels_error")
            logger.info(f"✅ استخرج {len(leads)} عميل محتمل")

        except Exception as e:
            logger.error(f"خطأ أثناء استخراج العملاء: {e}")
            await take_error_screenshot(self.page, "scrape_error")

        return leads

    # ─────────────────────────────────────────────────────────────
    #  التحقق من تسجيل الدخول
    # ─────────────────────────────────────────────────────────────

    async def _verify_logged_in(self) -> bool:
        try:
            current_url = self.page.url
            if "/accounts/login" in current_url or "/login" in current_url:
                logger.error(f"🚫 URL يشير لصفحة الدخول: {current_url}")
                return False

            page_text = await self.page.inner_text("body")
            login_indicators = [
                "Log in to Instagram",
                "تسجيل الدخول إلى إنستجرام",
                "Log In",
                "Log into Facebook",
            ]
            for indicator in login_indicators:
                if indicator.lower() in page_text.lower():
                    logger.error(f"🚫 مؤشر تسجيل دخول مكتشف: '{indicator}'")
                    return False

            logger.info("✅ الصفحة محملة - المستخدم مسجّل الدخول")
            return True
        except Exception as e:
            logger.warning(f"تعذّر فحص تسجيل الدخول: {e}")
            return True

    # ─────────────────────────────────────────────────────────────
    #  أدوات التشخيص
    # ─────────────────────────────────────────────────────────────

    async def _take_debug_screenshot(self, name: str):
        try:
            screenshots_dir = Path(cfg.SCREENSHOTS_DIR)
            screenshots_dir.mkdir(exist_ok=True)
            path = str(screenshots_dir / f"{name}.png")
            await self.page.screenshot(path=path, full_page=False)
            logger.info(f"📸 لقطة شاشة: {path}")
        except Exception as e:
            logger.warning(f"فشل التقاط لقطة: {e}")

    async def _log_element_counts(self):
        try:
            counts = await self.page.evaluate("""
                () => {
                    const area = document.querySelector('[role="dialog"]') ||
                                 document.querySelector('section') ||
                                 document.querySelector('article') ||
                                 document.querySelector('main') ||
                                 document.body;

                    const spansWithText = Array.from(area.querySelectorAll('span'))
                        .filter(el => el.innerText && el.innerText.trim().length > 1).length;

                    const liCount = area.querySelectorAll('li').length;
                    const ulCount = area.querySelectorAll('ul').length;
                    const roleListItems = area.querySelectorAll('[role="listitem"]').length;

                    const profileLinks = Array.from(area.querySelectorAll('a[href^="/"]'))
                        .filter(a => {
                            const p = a.getAttribute('href') || '';
                            return p.match(/^\/[^\/]+\/$/) &&
                                   !p.includes('/p/') && !p.includes('/explore/') &&
                                   !p.includes('/reels/') && !p.includes('/stories/') &&
                                   !p.includes('/accounts/');
                        }).length;

                    const header = document.querySelector('article header, header[role]');
                    let postAuthor = 'غير محدد';
                    if (header) {
                        const link = header.querySelector('a[href^="/"]');
                        if (link) postAuthor = (link.getAttribute('href') || '').replace(/\//g, '');
                    }

                    return { spansWithText, liCount, ulCount, roleListItems, profileLinks, postAuthor };
                }
            """)
            logger.info(
                f"📊 إحصاء | ul: {counts['ulCount']} | li: {counts['liCount']} | "
                f"listitem: {counts['roleListItems']} | روابط مستخدمين: {counts['profileLinks']} | "
                f"span نصي: {counts['spansWithText']} | صاحب المنشور: {counts['postAuthor']}"
            )
        except Exception as e:
            logger.warning(f"فشل إحصاء العناصر: {e}")

    # ─────────────────────────────────────────────────────────────
    #  التمرير وتحميل التعليقات
    # ─────────────────────────────────────────────────────────────

    async def _open_comments_section(self):
        try:
            selectors = [
                'button[aria-label*="omment"]',
                'button[aria-label*="Comment"]',
                'button[aria-label*="عليق"]',
                '[role="button"][aria-label*="omment"]',
                '[role="button"][aria-label*="Comment"]',
                'svg[aria-label*="Comment"]',
                'svg[aria-label*="omment"]',
                'a[href*="/comments/"]',
            ]
            for selector in selectors:
                el = await self.page.query_selector(selector)
                if el and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(3)
                    break
        except Exception:
            pass

    async def _force_open_reels_comments(self) -> bool:
        for attempt in range(2):
            try:
                clicked = await self._click_reels_comment_icon(use_offset=attempt == 1)
                if not clicked:
                    logger.warning("⚠️ لم يتم العثور على أيقونة تعليقات Reels في هذه المحاولة")
                    continue

                await asyncio.sleep(3)
                try:
                    await self.page.wait_for_selector('[role="dialog"]', timeout=7000)
                    logger.info("✅ تم فتح نافذة تعليقات Reels وظهر عنصر dialog")
                    return True
                except Exception:
                    logger.warning("⚠️ لم يظهر dialog بعد الضغط على تعليقات Reels")
            except Exception as e:
                logger.warning(f"تعذّرت محاولة فتح تعليقات Reels: {e}")

            if attempt == 0:
                logger.info("🔁 إعادة محاولة فتح تعليقات Reels بضغط Offset")

        return False

    async def _click_reels_comment_icon(self, use_offset: bool = False) -> bool:
        selectors = [
            'button[aria-label*="Comment"]',
            'button[aria-label*="comment"]',
            'button[aria-label*="تعليق"]',
            '[role="button"][aria-label*="Comment"]',
            '[role="button"][aria-label*="comment"]',
            '[role="button"][aria-label*="تعليق"]',
            'svg[aria-label*="Comment"]',
            'svg[aria-label*="comment"]',
            'svg[aria-label*="تعليق"]',
        ]

        for selector in selectors:
            try:
                el = await self.page.query_selector(selector)
                if not el:
                    continue
                target = await el.evaluate_handle("""
                    el => el.closest('button, [role="button"], a') || el
                """)
                try:
                    if use_offset:
                        box = await target.as_element().bounding_box()
                        if box:
                            await self.page.mouse.click(
                                box["x"] + (box["width"] * 0.60),
                                box["y"] + (box["height"] * 0.55)
                            )
                        else:
                            await target.as_element().click(force=True)
                    else:
                        await target.as_element().click(force=True)
                    logger.info(f"💬 تم الضغط على أيقونة التعليقات: {selector}")
                    return True
                except Exception:
                    clicked = await self.page.evaluate("""
                        selector => {
                            const el = document.querySelector(selector);
                            if (!el) return false;
                            const target = el.closest('button, [role="button"], a') || el;
                            target.click();
                            return true;
                        }
                    """, selector)
                    if clicked:
                        logger.info(f"💬 تم تنفيذ JavaScript click على أيقونة التعليقات: {selector}")
                        return True
            except Exception:
                continue

        try:
            clicked = await self.page.evaluate("""
                useOffset => {
                    const visible = el => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0 &&
                               rect.bottom > 0 && rect.right > 0 &&
                               rect.top < window.innerHeight && rect.left < window.innerWidth;
                    };
                    const textOf = el => (el?.innerText || el?.textContent || '').trim().toLowerCase();
                    const reelsRoots = [
                        document.querySelector('div[role="presentation"]'),
                        document.querySelector('div.x168nmei'),
                        document.querySelector('div[class*="x168nmei"]'),
                        document.querySelector('main'),
                        document.body
                    ].filter(Boolean);
                    const isCommentTarget = el => {
                        const aria = (el.getAttribute?.('aria-label') || '').toLowerCase();
                        const title = (el.getAttribute?.('title') || '').toLowerCase();
                        const text = textOf(el);
                        return aria.includes('comment') || aria.includes('تعليق') ||
                               title.includes('comment') || title.includes('تعليق') ||
                               text === 'comment' || text === 'تعليق' || text.includes('comments');
                    };
                    for (const root of reelsRoots) {
                        const candidates = Array.from(root.querySelectorAll('button, [role="button"], a, svg'))
                            .filter(el => visible(el) && isCommentTarget(el));
                        for (const el of candidates) {
                            const target = el.closest('button, [role="button"], a') || el;
                            if (useOffset) {
                                const rect = target.getBoundingClientRect();
                                const x = rect.left + rect.width * 0.60;
                                const y = rect.top + rect.height * 0.55;
                                const offsetTarget = document.elementFromPoint(x, y) || target;
                                offsetTarget.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX: x, clientY: y }));
                                offsetTarget.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: x, clientY: y }));
                                offsetTarget.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: x, clientY: y }));
                                offsetTarget.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: x, clientY: y }));
                            } else {
                                target.click();
                            }
                            return true;
                        }
                    }
                    const svgs = Array.from(document.querySelectorAll('svg')).filter(svg => {
                        const label = (svg.getAttribute('aria-label') || '').toLowerCase();
                        const pathCount = svg.querySelectorAll('path, polygon, circle').length;
                        return visible(svg) && (label.includes('comment') || label.includes('تعليق') || pathCount >= 1);
                    });
                    for (const svg of svgs) {
                        const target = svg.closest('button, [role="button"], a') || svg.parentElement;
                        if (!target || !visible(target)) continue;
                        target.click();
                        return true;
                    }
                    return false;
                }
            """, use_offset)
            if clicked:
                logger.info("💬 تم الضغط على SVG/عنصر تعليق Reels عبر JavaScript")
                return True
        except Exception as e:
            logger.warning(f"فشل JavaScript click لأيقونة تعليقات Reels: {e}")

        return False

    async def _wait_for_comments_content(self) -> bool:
        selectors = [
            '[role="dialog"] ul li',
            '[role="dialog"] [role="listitem"]',
            '[role="dialog"] div[role="presentation"] span',
            'div[role="presentation"] span',
            'div.x168nmei span',
            'div[class*="x168nmei"] span',
            'article ul li',
            'article [role="listitem"]',
            'main ul li',
            'main [role="listitem"]',
            'section ul li',
            'section [role="listitem"]',
            'ul[role="list"] li',
            'div[role="dialog"] a[href^="/"]',
            'article a[href^="/"]',
        ]
        try:
            await self.page.wait_for_selector(", ".join(selectors), timeout=5000)
            logger.info("✅ ظهرت عناصر التعليقات")
            return True
        except Exception:
            pass
        logger.warning("⚠️ لم تظهر عناصر التعليقات خلال 5 ثوانٍ - سيتم المتابعة بمحاولة التمرير")
        return False

    async def _get_loaded_comment_count(self) -> int:
        try:
            return await self.page.evaluate("""
                () => {
                    const area = document.querySelector('[role="dialog"]') ||
                                 document.querySelector('section') ||
                                 document.querySelector('article') ||
                                 document.querySelector('main') || document.body;
                    const seen = new Set();
                    area.querySelectorAll('a[href^="/"]').forEach(a => {
                        const p = a.getAttribute('href') || '';
                        if (p.match(/^\/[^\/]+\/$/) &&
                            !p.includes('/p/') && !p.includes('/explore/') &&
                            !p.includes('/reels/') && !p.includes('/stories/') &&
                            !p.includes('/accounts/')) {
                            seen.add(p);
                        }
                    });
                    return seen.size;
                }
            """)
        except Exception:
            return 0

    async def _focus_dialog_for_scroll(self):
        """يضغط داخل نافذة الـ dialog لضمان التركيز قبل بدء التمرير"""
        try:
            box = await self.page.evaluate("""
                () => {
                    const dialog = document.querySelector('[role="dialog"]');
                    if (!dialog) return null;
                    const rect = dialog.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return null;
                    return { x: rect.left + rect.width / 2,
                             y: rect.top + rect.height * 0.3,
                             w: rect.width, h: rect.height };
                }
            """)
            if box and box.get('w', 0) > 0:
                await self.page.mouse.click(box['x'], box['y'])
                await asyncio.sleep(0.5)
                logger.info("[🎯] تم التركيز داخل نافذة التعليقات")
        except Exception as e:
            logger.warning(f"تعذّر التركيز على dialog: {e}")

    async def _do_smart_scroll(self) -> bool:
        """
        تمرير ذكي بثلاث استراتيجيات مع التحقق من النجاح:
        1- JavaScript يبحث عن العنصر الفعلي القابل للتمرير داخل dialog
        2- Mouse wheel فوق مركز نافذة التعليقات
        3- Fallback شامل على جميع العناصر المحتملة
        """
        # ─── الاستراتيجية 1: JavaScript مع قياس scrollTop قبل/بعد ───
        result = await self.page.evaluate("""
            () => {
                const findScrollable = (root) => {
                    const walk = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                    let node = walk.nextNode();
                    while (node) {
                        const st = window.getComputedStyle(node);
                        if ((st.overflowY === 'auto' || st.overflowY === 'scroll') &&
                             node.scrollHeight > node.clientHeight + 10) return node;
                        node = walk.nextNode();
                    }
                    return root;
                };
                const dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return { success: false, reason: 'no-dialog' };
                const target = findScrollable(dialog);
                const before = target.scrollTop;
                target.scrollTop = target.scrollHeight;
                [dialog,
                 dialog.firstElementChild,
                 dialog.querySelector('ul'),
                 dialog.querySelector('div > div'),
                 dialog.querySelector('div > div > div')]
                .filter(Boolean)
                .forEach(el => { try { el.scrollTop = el.scrollHeight; } catch {} });
                const after = target.scrollTop;
                return { success: after > before, before, after, tag: target.tagName };
            }
        """)

        if result.get('success'):
            logger.debug(f"[✔] JS scroll نجح: {result.get('before')}→{result.get('after')} على <{result.get('tag')}>")
            return True

        logger.debug(f"[⚠] scrollTop لم يتغير ({result.get('before')}→{result.get('after')}) - محاولة Mouse Wheel")

        # ─── الاستراتيجية 2: Mouse Wheel فوق dialog ───
        try:
            box = await self.page.evaluate("""
                () => {
                    const dialog = document.querySelector('[role="dialog"]');
                    if (!dialog) return null;
                    const r = dialog.getBoundingClientRect();
                    return { x: r.left + r.width / 2, y: r.top + r.height * 0.6 };
                }
            """)
            if box:
                wheel_dist = random.randint(400, 700)
                await self.page.mouse.move(box['x'], box['y'])
                await self.page.mouse.wheel(0, wheel_dist)
                await asyncio.sleep(0.2)
                await self.page.mouse.wheel(0, wheel_dist + random.randint(-80, 80))
                logger.debug(f"[🖱️] Mouse wheel على dialog بمسافة {wheel_dist}")
                return True
        except Exception as e:
            logger.debug(f"Mouse wheel فشل: {e}")

        # ─── الاستراتيجية 3: Fallback عام ───
        try:
            await self.page.evaluate("""
                () => {
                    const sels = [
                        '[role="dialog"] ul',
                        '[role="dialog"] > div',
                        '[role="dialog"] > div > div',
                        'section ul', 'main ul', 'article ul',
                        'main', 'article'
                    ];
                    for (const s of sels) {
                        const el = document.querySelector(s);
                        if (el && el.scrollHeight > el.clientHeight)
                            el.scrollTop = el.scrollHeight;
                    }
                    window.scrollBy(0, 800);
                }
            """)
        except Exception:
            pass
        return False

    async def _wait_for_spinner(self):
        """ينتظر اختفاء أيقونة التحميل (Loading Spinner) إذا وُجدت"""
        try:
            spinner_sels = [
                '[aria-label*="Loading"]', '[aria-label*="تحميل"]',
                'svg[aria-label*="Loading"]', '[role="progressbar"]',
                'circle[class*="loading"]', '[data-testid*="spinner"]',
            ]
            for sel in spinner_sels:
                spinner = await self.page.query_selector(sel)
                if spinner and await spinner.is_visible():
                    try:
                        await self.page.wait_for_selector(
                            sel, state="hidden", timeout=4000
                        )
                    except Exception:
                        pass
                    break
        except Exception:
            pass

    async def _final_load_more_check(self):
        """فحص نهائي: ضغط على أي زر 'تحميل المزيد' ظاهر قبل الخروج"""
        btns_texts = [
            "Load more comments", "تحميل المزيد من التعليقات",
            "View more replies", "مشاهدة المزيد من الردود",
            "Load more", "تحميل المزيد",
            "View replies", "عرض الردود",
        ]
        selectors = (
            [f'span[role="button"]:has-text("{t}")' for t in btns_texts] +
            [f'button:has-text("{t}")' for t in btns_texts] +
            ['[role="button"][aria-label*="Load more"]',
             '[role="button"][aria-label*="تحميل المزيد"]']
        )
        clicked = 0
        for sel in selectors:
            try:
                buttons = await self.page.query_selector_all(sel)
                for btn in buttons:
                    if await btn.is_visible():
                        await btn.click()
                        clicked += 1
                        await asyncio.sleep(1.5)
            except Exception:
                continue
        if clicked:
            logger.info(f"[🔁] الفحص النهائي: ضُغط على {clicked} زر تحميل مزيد")
            await asyncio.sleep(2)

    async def _scroll_to_load_comments(self) -> tuple[int, int]:
        scroll_count, empty_scrolls, total_new = 0, 0, 0
        previous_count = await self._get_loaded_comment_count()

        # ← تركيز داخل النافذة قبل بدء السكرول
        await self._focus_dialog_for_scroll()

        try:
            for i in range(cfg.MAX_COMMENTS_SCROLL):
                await self._do_smart_scroll()
                # تأخير ديناميكي: 0.5-1.0 ثانية للسماح بتحميل التعليقات الجديدة
                await random_delay(0.5, 1.0)
                await self._click_load_more_comments()
                scroll_count += 1

                # ── Lazy Loading Buffer: توقف 2 ثانية كل 5 تمريرات ──
                if scroll_count % 5 == 0:
                    logger.info(f"[⏳] توقف مؤقت للـ Lazy Loading بعد {scroll_count} تمريرة...")
                    await self._wait_for_spinner()
                    await asyncio.sleep(2.0)

                current_count = await self._get_loaded_comment_count()
                new_comments = max(current_count - previous_count, 0)
                total_new += new_comments
                previous_count = current_count

                logger.info(f"[📊] جاري سحب المزيد.. الإجمالي الحالي: {current_count} تعليق")

                empty_scrolls = 0 if new_comments > 0 else empty_scrolls + 1
                if total_new >= self.target_new_comments:
                    logger.info(f"[✅] تم الوصول للعدد المطلوب: {total_new} تعليق جديد")
                    break
                if empty_scrolls >= 6:
                    logger.info(f"[⛔] لا تعليقات جديدة بعد 6 تمريرات متتالية - إيقاف السحب")
                    break
        except Exception as e:
            logger.error(f"خطأ أثناء التمرير: {e}")

        # ── الفحص النهائي: ضغط على أي زر تحميل مزيد ظاهر ──
        if previous_count < self.target_new_comments:
            await self._final_load_more_check()
            final_count = await self._get_loaded_comment_count()
            if final_count > previous_count:
                logger.info(f"[📈] الفحص النهائي أضاف {final_count - previous_count} تعليق إضافي")
                previous_count = final_count

        return scroll_count, previous_count

    async def _extra_scroll_for_comments(self):
        try:
            await self.page.evaluate("""
                () => {
                    const containers = [
                        document.querySelector('[role="dialog"] ul'),
                        document.querySelector('[role="dialog"]'),
                        document.querySelector('section ul'),
                        document.querySelector('main ul'),
                        document.querySelector('article ul'),
                        document.querySelector('main'),
                        document.scrollingElement,
                        document.documentElement,
                        document.body
                    ].filter(Boolean);
                    for (const container of containers) {
                        try {
                            container.scrollTop = container.scrollHeight;
                        } catch {}
                    }
                    window.scrollBy(0, 1200);
                }
            """)
        except Exception as e:
            logger.warning(f"تعذّر تنفيذ Scroll التحقق الإضافي: {e}")

    async def _click_load_more_comments(self):
        selectors = [
            'button[aria-label*="Load more"]',
            'button[aria-label*="تحميل المزيد"]',
            'span[role="button"]:has-text("Load more")',
            'span[role="button"]:has-text("تحميل المزيد")',
        ]
        for selector in selectors:
            try:
                btn = await self.page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click()
                    await random_delay(1, 2)
                    break
            except Exception:
                continue

    async def _click_view_replies(self):
        """
        يضغط على كل أزرار 'View replies' / 'مشاهدة الردود' لكشف الردود المخفية.
        يستمر حتى لا يجد أزراراً جديدة.
        """
        reply_texts = [
            "View replies", "View reply",
            "مشاهدة الردود", "مشاهدة الرد",
            "عرض الردود", "عرض الرد",
        ]
        selectors = [
            f'span[role="button"]:has-text("{t}")' for t in reply_texts
        ] + [
            f'button:has-text("{t}")' for t in reply_texts
        ] + [
            'span[role="button"][aria-label*="repl"]',
            'button[aria-label*="repl"]',
        ]

        clicked_total = 0
        for _round in range(5):
            clicked_this_round = 0
            for selector in selectors:
                try:
                    buttons = await self.page.query_selector_all(selector)
                    for btn in buttons:
                        try:
                            if await btn.is_visible():
                                await btn.click()
                                await random_delay(0.8, 1.5)
                                clicked_this_round += 1
                        except Exception:
                            continue
                except Exception:
                    continue
            clicked_total += clicked_this_round
            if clicked_this_round == 0:
                break
            await random_delay(1, 2)

        if clicked_total:
            logger.info(f"🔽 تم فتح {clicked_total} ردود مخفية (View replies)")

    # ─────────────────────────────────────────────────────────────
    #  استخراج العملاء - الاستراتيجية المحسّنة
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _has_real_text(text: str) -> bool:
        """يقبل أي نص يحتوي على حرف واحد على الأقل (عربي أو إنجليزي)"""
        return bool(_HAS_LETTER.search(text))

    async def _extract_leads_from_comments(self, post_url: str) -> list[dict]:
        """
        استخراج التعليقات الفعلية باستخدام Parent-Scan و JavaScript ذكي.
        """
        leads = []
        seen_usernames = set()
        logged_in_user = (cfg.INSTAGRAM_USERNAME or "").strip().lower()

        try:
            raw = await self.page.evaluate("""
                (loggedInUser) => {
                    const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();

                    const cleanHref = href => {
                        if (!href) return '';
                        let path = href;
                        try { path = href.startsWith('http') ? new URL(href).pathname : href; } catch {}
                        return path.replace(/^\//, '').replace(/\/$/, '').trim();
                    };

                    const isProfileHref = href => {
                        if (!href) return false;
                        const p = href.startsWith('/') ? href : (() => {
                            try { return new URL(href).pathname; } catch { return href; }
                        })();
                        return /^\/[^\/]+\/$/.test(p) &&
                               !p.includes('/p/') && !p.includes('/explore/') &&
                               !p.includes('/reels/') && !p.includes('/stories/') &&
                               !p.includes('/accounts/') && !p.includes('/tags/') &&
                               !p.includes('/direct/') && !p.includes('/about/') &&
                               !p.includes('/privacy/') && !p.includes('/legal/');
                    };

                    const getPostAuthor = () => {
                        const headerSelectors = [
                            'article header',
                            'div[role="dialog"] header',
                            'div[role="presentation"] header',
                            'main header',
                            'header'
                        ];
                        for (const selector of headerSelectors) {
                            const header = document.querySelector(selector);
                            if (!header) continue;
                            const links = Array.from(header.querySelectorAll('a[href]'))
                                .filter(a => isProfileHref(a.getAttribute('href')));
                            if (links.length) return cleanHref(links[0].getAttribute('href'));
                        }
                        const roots = [
                            document.querySelector('[role="dialog"]'),
                            document.querySelector('div[role="presentation"]'),
                            document.querySelector('div.x168nmei'),
                            document.querySelector('div[class*="x168nmei"]'),
                            document.querySelector('article'),
                            document.querySelector('main'),
                            document.body
                        ].filter(Boolean);
                        for (const root of roots) {
                            for (const link of root.querySelectorAll('a[href]')) {
                                if (isProfileHref(link.getAttribute('href'))) {
                                    return cleanHref(link.getAttribute('href'));
                                }
                            }
                        }
                        return null;
                    };

                    const getSearchRoots = () => {
                        const roots = [
                            document.querySelector('[role="dialog"]'),
                            document.querySelector('div[role="presentation"]'),
                            document.querySelector('div.x168nmei'),
                            document.querySelector('div[class*="x168nmei"]'),
                            document.querySelector('section'),
                            document.querySelector('article'),
                            document.querySelector('main'),
                            document.body
                        ].filter(Boolean);
                        return roots.filter((root, index) => roots.indexOf(root) === index);
                    };

                    const getRootProfileLinks = roots => {
                        const seenHrefs = new Set();
                        const links = [];
                        for (const root of roots) {
                            for (const link of root.querySelectorAll('a[href]')) {
                                const href = link.getAttribute('href') || '';
                                if (!isProfileHref(href)) continue;
                                const key = cleanHref(href).toLowerCase();
                                if (!key || seenHrefs.has(key + '::' + textOf(link))) continue;
                                seenHrefs.add(key + '::' + textOf(link));
                                links.push(link);
                            }
                        }
                        return links;
                    };

                    const extractLooseReelsRows = roots => {
                        const rows = [];
                        for (const root of roots) {
                            const containers = Array.from(root.querySelectorAll(
                                'div.x168nmei, div[class*="x168nmei"], div[role="presentation"], ul li, [role="listitem"]'
                            ));
                            for (const container of containers) {
                                const links = Array.from(container.querySelectorAll('a[href]')).filter(a => isProfileHref(a.getAttribute('href')));
                                const spans = Array.from(container.querySelectorAll('span'))
                                    .map(textOf)
                                    .filter(Boolean)
                                    .filter(text => !badText(text));
                                for (const link of links) {
                                    const username = cleanHref(link.getAttribute('href'));
                                    const text = spans.find(spanText => spanText.toLowerCase() !== username.toLowerCase());
                                    if (username && text) rows.push({ username, text, method: 'reels-container-scan' });
                                }
                            }
                        }
                        return rows;
                    };

                    const postAuthor = getPostAuthor();
                    const blacklist = new Set();
                    blacklist.add('applewinning10');
                    if (postAuthor) blacklist.add(postAuthor.toLowerCase());
                    if (loggedInUser) blacklist.add(loggedInUser.toLowerCase());

                    const badText = text => {
                        const t = (text || '').replace(/\s+/g, ' ').trim();
                        const low = t.toLowerCase();
                        if (t.length < 2) return true;
                        if (/^\d+(w|h|m|d|s|ث|د|س|ي)?$/i.test(t)) return true;
                        if (/^[•·.]+$/.test(t)) return true;
                        return [
                            'follow', 'following', 'reply', 'replies', 'view replies',
                            'see translation', 'translation', 'like', 'liked',
                            'متابعة', 'يتابع', 'رد', 'الرد', 'ردود', 'عرض الردود',
                            'مشاهدة الردود', 'أعجبني', 'ترجمة', 'عرض الترجمة'
                        ].some(word => low.includes(word));
                    };

                    const isCleanSpan = (span, username) => {
                        if (!span || span.closest('a[href]')) return false;
                        if (span.querySelector('a[href]')) return false;
                        if (span.closest('time, button, [role="button"]')) return false;
                        const text = textOf(span);
                        if (!text || text.toLowerCase() === (username || '').toLowerCase()) return false;
                        return !badText(text);
                    };

                    const nearestCommentRoot = link => {
                        const preferred = link.closest('li, [role="listitem"], div.x168nmei, div[class*="x168nmei"], div[role="presentation"]');
                        if (preferred) return preferred;
                        let node = link.parentElement;
                        for (let depth = 0; node && depth < 9; depth += 1) {
                            const profileLinks = Array.from(node.querySelectorAll('a[href]'))
                                .filter(a => isProfileHref(a.getAttribute('href')));
                            const spans = Array.from(node.querySelectorAll('span')).filter(s => textOf(s).length > 1);
                            if (profileLinks.length >= 1 && spans.length >= 2) return node;
                            node = node.parentElement;
                        }
                        return link.parentElement;
                    };

                    const textFromParentScan = (link, username) => {
                        let node = link.parentElement;
                        for (let depth = 0; node && depth < 9; depth += 1) {
                            const spans = Array.from(node.querySelectorAll('span'))
                                .filter(span => isCleanSpan(span, username))
                                .map(textOf)
                                .filter((text, index, arr) => arr.indexOf(text) === index);
                            const direct = spans.find(text => text.length > 1);
                            if (direct) return direct;
                            node = node.parentElement;
                        }
                        return '';
                    };

                    const textAfterUsername = (link, username) => {
                        const root = nearestCommentRoot(link);
                        if (!root) return '';
                        const profileLinks = new Set(
                            Array.from(root.querySelectorAll('a[href]'))
                                .filter(a => isProfileHref(a.getAttribute('href')))
                        );
                        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                        const pieces = [];
                        let collecting = false;
                        while (walker.nextNode()) {
                            const node = walker.currentNode;
                            const parent = node.parentElement;
                            if (!parent) continue;
                            const value = (node.nodeValue || '').replace(/\s+/g, ' ').trim();
                            if (!value) continue;
                            const ownerLink = parent.closest('a[href]');
                            if (ownerLink === link || value.toLowerCase() === username.toLowerCase()) {
                                collecting = true;
                                continue;
                            }
                            if (!collecting) continue;
                            if (ownerLink && profileLinks.has(ownerLink)) break;
                            if (parent.closest('time, button, [role="button"]')) continue;
                            if (badText(value)) continue;
                            if (value.toLowerCase() === username.toLowerCase()) continue;
                            pieces.push(value);
                            if (pieces.join(' ').length >= 180) break;
                        }
                        return pieces.join(' ').replace(/\s+/g, ' ').trim();
                    };

                    const escapeRegex = value => value.replace(/[-/\\^$*+?.()|[\]{}]/g, '\\$&');

                    const textByCloneCleanup = (link, username) => {
                        const root = nearestCommentRoot(link);
                        if (!root) return '';
                        const clone = root.cloneNode(true);
                        clone.querySelectorAll('a[href], time, button, [role="button"]').forEach(el => el.remove());
                        const text = textOf(clone)
                            .replace(new RegExp('^' + escapeRegex(username) + '\\b', 'i'), '')
                            .trim();
                        return badText(text) ? '' : text;
                    };

                    const searchRoots = getSearchRoots();
                    const profileLinks = getRootProfileLinks(searchRoots);
                    const results = [];
                    const debugSamples = [];
                    const seen = new Set();

                    const addResult = (username, rawText, method) => {
                        if (!username || username.includes('/') || username.length < 2) return;
                        if (blacklist.has(username.toLowerCase())) return;
                        const text = (rawText || '').replace(/\s+/g, ' ').trim();
                        debugSamples.push({ username, text: text || '(فارغ)', method });
                        if (!text || text.toLowerCase() === username.toLowerCase()) return;
                        if (badText(text)) return;
                        const key = username.toLowerCase() + '::' + text.substring(0, 120).toLowerCase();
                        if (seen.has(key)) return;
                        seen.add(key);
                        results.push({ username, text, method });
                    };

                    for (const link of profileLinks) {
                        const username = cleanHref(link.getAttribute('href'));
                        if (!username || blacklist.has(username.toLowerCase())) continue;
                        const parentText = textFromParentScan(link, username);
                        const followingText = textAfterUsername(link, username);
                        const fallbackText = textByCloneCleanup(link, username);
                        const method = parentText ? 'parent-scan' : followingText ? 'evaluate-next-text' : 'clone-cleanup';
                        addResult(username, parentText || followingText || fallbackText, method);
                    }

                    for (const item of extractLooseReelsRows(searchRoots)) {
                        addResult(item.username, item.text, item.method);
                    }

                    return {
                        postAuthor,
                        blacklist: [...blacklist],
                        profileLinksSeen: profileLinks.length,
                        debugSamples: debugSamples.slice(0, 15),
                        results
                    };
                }
            """, logged_in_user)

            post_author = raw.get("postAuthor") or "غير محدد"
            comments_data = raw.get("results", [])
            total_comments = len(comments_data)

            # سطر واحد مختصر فقط
            logger.info(
                f"PROGRESS_COMMENTS total={total_comments} checked=0 leads=0"
            )

            batch_logged = False
            for checked, item in enumerate(comments_data, 1):
                # طباعة مرة كل 20 عميل فقط
                if checked % 20 == 1 and not batch_logged:
                    logger.info(f"[⚡] جاري معالجة مجموعة تعليقات...")
                    batch_logged = False
                if checked % 20 == 0:
                    logger.info(
                        f"PROGRESS_COMMENTS total={total_comments} "
                        f"checked={checked} leads={len(leads)}"
                    )
                    batch_logged = True
                else:
                    batch_logged = False

                username = item.get("username", "").strip()
                comment_text = item.get("text", "").strip()

                if not username or username in seen_usernames:
                    continue
                if "/" in username or len(username) < 2:
                    continue
                if username.lower() == logged_in_user:
                    continue
                if post_author and username.lower() == post_author.lower():
                    continue
                if comment_text.lower() == username.lower():
                    logger.debug(f"تخطي @{username} - النص هو الاسم نفسه")
                    continue

                if self._has_real_text(comment_text):
                    seen_usernames.add(username)
                    leads.append({
                        "username": username,
                        "comment_text": comment_text,
                        "post_url": post_url,
                    })

                    pass  # تمت إضافة العميل للقائمة

                if checked == total_comments:
                    logger.info(
                        f"PROGRESS_COMMENTS total={total_comments} "
                        f"checked={checked} leads={len(leads)}"
                    )

        except Exception as e:
            logger.error(f"خطأ في استخراج التعليقات: {e}")
            await take_error_screenshot(self.page, "extract_comments_error")

        return leads

    def set_keywords(self, keywords: list):
        self.keywords = keywords
