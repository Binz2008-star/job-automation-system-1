# Self-Hosted GitHub Actions Runner Setup

## مرحلة الإنتاج الكامل - Fully Automated System

هذا الدليل يوضح كيفية إعداد نظام التوظيف التلقائي الكامل باستخدام GitHub Actions self-hosted runner.

## الخطة المعمارية (Architecture Plan)

```text
GitHub-hosted runner (intelligence) → self-hosted runner (apply) → Gmail (track) → dashboard (report)
```

### المرحلة 1: تسجيل Self-Hosted Runner

1. **في GitHub Repository:**
   - Settings → Actions → Runners → New self-hosted runner
   - اختر Linux x64 أو Windows حسب جهازك

2. **تنزيل وتثبيت Runner:**
```powershell
# إنشاء مجلد العمل
mkdir C:\runner
cd C:\runner

# تحميل runner
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-win-x64-2.311.0.zip -OutFile actions-runner.zip
Expand-Archive -LiteralPath actions-runner.zip -DestinationPath .

# تثبيت runner
.\config.cmd --url https://github.com/Binz2008-star/job-automation-system-1 --token YOUR_TOKEN_HERE

# تشغيل runner كخدمة
.\run.cmd
```

3. **تسجيل Runner كخدمة (Windows):**
```powershell
# إنشاء خدمة Windows
New-Service -Name "github-runner" -BinaryPathName "C:\runner\run.cmd" -DisplayName "GitHub Actions Runner" -StartupType Automatic

# تشغيل الخدمة
Start-Service -Name "github-runner"
```

## المرحلة 2: تعديل Workflow للعمل المزدوج

### تحديث `.github/workflows/daily-job-bot.yml`:

```yaml
name: Daily Job Bot

on:
  schedule:
    - cron: '0 6 * * *'  # كل يوم الساعة 6
  workflow_dispatch:

jobs:
  # Job 1: Intelligence (GitHub-hosted)
  intelligence:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install --with-deps
      
      - name: Run intelligence pipeline
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GMAIL_CREDENTIALS_JSON: ${{ secrets.GMAIL_CREDENTIALS_JSON }}
          GMAIL_TOKEN_JSON: ${{ secrets.GMAIL_TOKEN_JSON }}
          EMAIL_USER: ${{ secrets.EMAIL_USER }}
          EMAIL_PASS: ${{ secrets.EMAIL_PASS }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
          # NaukriGulf disabled for intelligence job
          NG_ENABLED: "false"
          EXCLUDE_KEYWORDS: ${{ secrets.EXCLUDE_KEYWORDS }}
        run: |
          python -m src.run_daily

  # Job 2: Browser Automation (Self-hosted)
  apply:
    runs-on: self-hosted  # يستخدم جهازك
    needs: intelligence
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install --with-deps
      
      - name: Run NaukriGulf automation
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GMAIL_CREDENTIALS_JSON: ${{ secrets.GMAIL_CREDENTIALS_JSON }}
          GMAIL_TOKEN_JSON: ${{ secrets.GMAIL_TOKEN_JSON }}
          EMAIL_USER: ${{ secrets.EMAIL_USER }}
          EMAIL_PASS: ${{ secrets.EMAIL_PASS }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
          # NaukriGulf enabled for apply job
          NG_ENABLED: "true"
          NG_FORCE_GITHUB_BROWSER: "true"
          NG_DRY_RUN: "false"
          NG_MAX_PER_RUN: "2"
          NG_DAILY_LIMIT: "5"
          NG_SCORE_THRESHOLD: "85"
          NG_HEADLESS: "true"
          NAUKRIGULF_EMAIL: ${{ secrets.NAUKRIGULF_EMAIL }}
          NAUKRIGULF_PASSWORD: ${{ secrets.NAUKRIGULF_PASSWORD }}
          EXCLUDE_KEYWORDS: ${{ secrets.EXCLUDE_KEYWORDS }}
        run: |
          python -c "
from src.naukrigulf_apply import run_naukrigulf_apply
results = run_naukrigulf_apply(max_applies=2)
print(f'Applied: {sum(1 for r in results if r.status == \"success\")} jobs')
          "
```

## المرحلة 3: متغيرات البيئة المطلوبة

### إضافة Secrets إلى GitHub:

```env
# Intelligence Job (GitHub-hosted)
NG_ENABLED=false
EXCLUDE_KEYWORDS=quantity surveyor,surveyor,purchasing,procurement,interior,joinery,architect,civil engineer,project engineer,hr officer,catering,accommodation,cad supervisor,technician,driver,consultant,recruitment agency,admin officer,secretary,personal assistant,uae national,emirati only,operations manager,general manager,executive assistant,store manager,sales manager,marketing manager,business development manager

# Apply Job (Self-hosted)
NG_FORCE_GITHUB_BROWSER=true
NG_MAX_PER_RUN=2
NG_DAILY_LIMIT=5
NG_SCORE_THRESHOLD=85
NG_HEADLESS=true
```

## المرحلة 4: اختبار التشغيل التلقائي

### اختبار النظام:
```bash
# تشغيل يدوي للاختبار
gh workflow run "Daily Job Bot"

# مراقبة التشغيل
gh run watch RUN_ID --exit-status
```

### النتائج المتوقعة:
- **Intelligence Job**: يجلب ويقيم الوظائف في ~2 دقيقة
- **Apply Job**: يتقدم للوظائف المستهدفة تلقائياً
- **Gmail**: يتلقى تأكيدات المقابلات
- **Dashboard**: يعرض التقارير والتحكم
- **Telegram**: يرسل إشعارات فورية

## المرحلة 5: الصيانة والمراقبة

### مراقبة الخدمة (Windows):
```powershell
# فحص حالة الخدمة
Get-Service -Name "github-runner"

# إعادة تشغيل عند الفشل
Restart-Service -Name "github-runner" -Force
```

### تحديثات تلقائية:
```powershell
# تحديث runner تلقائياً
cd C:\runner
.\config.cmd --url https://github.com/Binz2008-star/job-automation-system-1 --token YOUR_TOKEN_HERE --replace
```

## خلاصة النظام الكامل

```text
الساعة 6 صباحاً:
┌─────────────────────────────────────────┐
│ GitHub-hosted Intelligence Job     │
│ - يجلب الوظائف                 │
│ - يقيم ويصفي                │
│ - يرسل إشعارات Telegram         │
│ - يحدث Dashboard               │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│ Self-hosted Apply Job             │
│ - يتقدم للوظائف المستهدفة        │
│ - يستخدم NaukriGulf automation    │
│ - يتتبع مع Gmail                 │
└─────────────────────────────────────────┘
```

## استكشاف الأخطاء

### مشاكل شائعة وحلولها:

1. **Runner لا يظهر:**
   - تحقق من التوكل: `ping github.com`
   - أعد تشغيل الخدمة: `Restart-Service github-runner`

2. **Workflow لا يبدأ:**
   - تحقق من التوكن: انتهت صلاحيته؟
   - تحقق من الصلاحيات: هل runner لديه `self-hosted` tag؟

3. **NaukriGulf لا يعمل:**
   - تحقق من المتغيرات: `NG_ENABLED=true`
   - تحقق من الشبكة: هل جهازك يمكن الوصول لـ naukrigulf.com؟

## النتائج النهائية

بهذا الإعداد، ستحصل على:

✅ **نظام توظيف تلقائي بالكامل**  
✅ **تطبيقات مستهدفة ودقيقة**  
✅ **تتبع شامل مع Gmail**  
✅ **تحكم وتقارير فورية**  
✅ **تشغيل بدون تدخل بشري**  

النظام جاهز للعمل الإنتاجي الكامل!
