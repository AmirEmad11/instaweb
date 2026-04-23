# 📘 تثبيت Instagram Lead Bot مباشرة على VPS Ubuntu 24.04 (بدون Docker)

دليل شامل بالعربي للتشغيل المباشر باستخدام Python venv + systemd.
يحتوي على **خدمتين**:
- `instagram-bot` — البوت الرئيسي (Playwright + IPv6 Rotation + Stealth)
- `instagram-dashboard` — لوحة Streamlit للمتابعة من المتصفح على بورت **8080**

---

## 🟢 المتطلبات
- VPS فيه **Ubuntu 24.04**
- صلاحيات **root** أو مستخدم عنده **sudo**
- بريفكس IPv6 (افتراضي في الكود: `2a02:4780:28:421::/64`)
- اسم واجهة الشبكة (افتراضي `eth0`، اعرفه بـ `ip -br a`)

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

## 🔹 الخطوة 3: عدّل بيانات الحساب والمنشورات
```bash
nano instagram_automation/config.py     # اليوزر والباسورد
nano instagram_automation/main.py       # روابط المنشورات في TARGET_POSTS
```

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
5. ربط بريفكس IPv6 بالواجهة وتفعيل `ip_nonlocal_bind`.
6. إنشاء **خدمتين systemd**:
   - `instagram-bot` (البوت الرئيسي)
   - `instagram-dashboard` (لوحة Streamlit على بورت 8080)
7. فتح بورت 8080 في الفايروول لو UFW مفعّل.

> لو الواجهة عندك مش `eth0`:
> ```bash
> IPV6_INTERFACE=ens3 bash setup_vps.sh
> ```
> ولو عايز بورت تاني للوحة:
> ```bash
> DASHBOARD_PORT=9000 bash setup_vps.sh
> ```

## 🔹 الخطوة 5: شغّل الخدمتين
```bash
sudo systemctl start instagram-bot
sudo systemctl start instagram-dashboard
```

## 🔹 الخطوة 6: افتح اللوحة في المتصفح
```
http://YOUR_VPS_IP:8080
```

## 🔹 الخطوة 7: تابع اللوجز
```bash
# لوجز البوت
sudo journalctl -u instagram-bot -f

# لوجز اللوحة
sudo journalctl -u instagram-dashboard -f
```

---

## 📊 أوامر التحكم اليومية

### للبوت
| الوظيفة | الأمر |
|---------|------|
| تشغيل | `sudo systemctl start instagram-bot` |
| إيقاف | `sudo systemctl stop instagram-bot` |
| إعادة تشغيل | `sudo systemctl restart instagram-bot` |
| الحالة | `sudo systemctl status instagram-bot` |
| لوجز لحظية | `sudo journalctl -u instagram-bot -f` |
| تشغيل مرة بدون systemd | `bash run.sh` |

### للوحة
| الوظيفة | الأمر |
|---------|------|
| تشغيل | `sudo systemctl start instagram-dashboard` |
| إيقاف | `sudo systemctl stop instagram-dashboard` |
| إعادة تشغيل | `sudo systemctl restart instagram-dashboard` |
| الحالة | `sudo systemctl status instagram-dashboard` |
| لوجز لحظية | `sudo journalctl -u instagram-dashboard -f` |

### تحديث الكود من GitHub
```bash
git pull
sudo systemctl restart instagram-bot
sudo systemctl restart instagram-dashboard
```

---

## 🔐 فتح بورت 8080 يدوياً (لو UFW مش مفعّل من السكربت)
```bash
sudo ufw allow 22/tcp
sudo ufw allow 8080/tcp
sudo ufw --force enable
```

> ⚠️ لو السيرفر عند Hetzner/DigitalOcean/AWS، تأكد كمان من الـ Firewall الخارجي بتاعهم.

---

## 🌐 IPv6 Rotation
- وحدة `instagram_automation/ipv6_rotator.py` بتولّد IPv6 عشوائي من `2a02:4780:28:421::/64` وتربطه بالواجهة قبل كل تشغيل.
- في اللوجز:
  ```
  [IPv6] Using IP: 2a02:4780:28:421:xxxx:xxxx:xxxx:xxxx
  [IPv6] Bound 2a02:4780:28:421:xxxx:... to eth0
  ```

## 🛡️ Anti-Detection
- `playwright-stealth` بيتطبّق تلقائياً على كل صفحة جديدة:
  ```
  [BOT] playwright-stealth applied
  [BOT] Browser context ready - Starting Search
  ```

---

## 🛠 حل المشاكل

### اللوحة مش بتفتح في المتصفح؟
```bash
sudo systemctl status instagram-dashboard
sudo ss -tlnp | grep 8080
sudo ufw status
curl http://localhost:8080
```

### الخدمة فشلت؟
```bash
sudo journalctl -u instagram-bot -n 100 --no-pager
sudo journalctl -u instagram-dashboard -n 100 --no-pager
```

### عايز تبدأ من الصفر
```bash
sudo systemctl stop instagram-bot instagram-dashboard
rm -rf .venv
bash setup_vps.sh
```

بالتوفيق 🚀
