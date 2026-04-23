# 📘 تثبيت Instagram Lead Bot مباشرة على VPS Ubuntu 24.04 (بدون Docker)

دليل شامل بالعربي للتشغيل المباشر باستخدام Python venv + systemd.

---

## 🟢 المتطلبات
- VPS فيه **Ubuntu 24.04**
- صلاحيات **root** أو مستخدم عنده **sudo**
- بريفكس IPv6 مخصّص (في الكود: `2a02:4780:28:421::/64`)
- اسم واجهة الشبكة (افتراضي `eth0`، اعرفه بـ `ip a`)

---

## 🔹 الخطوة 1: ادخل على السيرفر
```bash
ssh root@YOUR_VPS_IP
```

## 🔹 الخطوة 2: اسحب المشروع من GitHub
```bash
cd /root
git clone https://github.com/USERNAME/REPO_NAME.git Instagram-Lead-Bot
cd Instagram-Lead-Bot
```

## 🔹 الخطوة 3: عدّل بيانات الحساب
```bash
nano instagram_automation/config.py
```
عدّل `INSTAGRAM_USERNAME` و `INSTAGRAM_PASSWORD` وأضف روابط المنشورات في `instagram_automation/main.py` داخل قائمة `TARGET_POSTS`.

## 🔹 الخطوة 4: شغّل سكربت التثبيت الكامل
```bash
chmod +x setup_vps.sh run.sh
bash setup_vps.sh
```
السكربت بيعمل تلقائياً:
1. تحديث النظام وتثبيت `python3-venv` و `fonts-noto` و `fonts-arabeyes`.
2. إنشاء `.venv` وتفعيله.
3. تثبيت كل المكتبات من `requirements.txt`.
4. تثبيت متصفح Chromium لـ Playwright.
5. ربط بريفكس IPv6 `2a02:4780:28:421::/64` بالواجهة.
6. إنشاء خدمة `systemd` اسمها `instagram-bot`.

> لو اسم الواجهة عندك مش `eth0`، شغّل بدلاً من ذلك:
> ```bash
> IPV6_INTERFACE=ens3 bash setup_vps.sh
> ```

## 🔹 الخطوة 5: شغّل البوت
```bash
sudo systemctl start instagram-bot
```

## 🔹 الخطوة 6: تابع اللوجز
```bash
sudo journalctl -u instagram-bot -f
# أو
tail -f /var/log/instagram-bot.log
```

---

## 📊 أوامر التحكم اليومية

| الوظيفة | الأمر |
|---------|------|
| تشغيل | `sudo systemctl start instagram-bot` |
| إيقاف | `sudo systemctl stop instagram-bot` |
| إعادة تشغيل | `sudo systemctl restart instagram-bot` |
| الحالة | `sudo systemctl status instagram-bot` |
| لوجز لحظية | `sudo journalctl -u instagram-bot -f` |
| تشغيل مرة واحدة بدون systemd | `bash run.sh` |
| تحديث الكود من GitHub | `git pull && sudo systemctl restart instagram-bot` |

---

## 🌐 IPv6 Rotation
- وحدة `instagram_automation/ipv6_rotator.py` بتولّد IPv6 عشوائي من البريفكس وتربطه بالواجهة قبل كل تشغيل.
- في اللوجز هتلاقي:
  ```
  [IPv6] Using IP: 2a02:4780:28:421:xxxx:xxxx:xxxx:xxxx
  [IPv6] Bound 2a02:4780:28:421:xxxx:... to eth0
  ```
- `setup_vps.sh` بيفعّل `net.ipv6.ip_nonlocal_bind=1` ويضيف route للبريفكس عشان الكيرنل يقبل أي IP من البريفكس كـ source address.

## 🛡️ Anti-Detection
- `playwright-stealth` بيتطبّق تلقائياً على كل صفحة جديدة.
- في اللوجز:
  ```
  [BOT] playwright-stealth applied
  [BOT] Browser context ready - Starting Search
  ```

---

## 🛠 حل المشاكل

### الواجهة مش `eth0`
```bash
ip -br a       # شوف اسم الواجهة الحقيقي
IPV6_INTERFACE=ens3 bash setup_vps.sh
```

### الخدمة مش بتشتغل
```bash
sudo systemctl status instagram-bot
sudo journalctl -u instagram-bot -n 100 --no-pager
```

### عايز تبدأ من الصفر
```bash
sudo systemctl stop instagram-bot
rm -rf .venv
bash setup_vps.sh
```

بالتوفيق 🚀
