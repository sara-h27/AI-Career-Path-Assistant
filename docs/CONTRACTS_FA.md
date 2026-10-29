# قرارداد اتصال UI، Dialogue AI و گراف — نسخهٔ ۱٫۰

## مرز مسئولیت‌ها

| جزء | ورودی | خروجی |
|---|---|---|
| ConversationManager | session_id و متن کاربر / ویرایش معتبر فرم | TurnResponse |
| مدل استخراج | پیام نرمال‌شده، وضعیت، پروفایل و شناسه‌های تاکسونومی | TurnExtractionSchema |
| GraphEngine | UserProfile معتبر و revision | Roadmap با همان revision و fingerprint |
| RoadmapSummarizer | همان Roadmap معتبر | متن فارسی مبتنی بر گره‌ها، ترتیب و یال‌های همان گراف |

## رابط پایتون

```python
from dialogue import ConversationManager, TaxonomyGuardrail, MockLLMClient

taxonomy = TaxonomyGuardrail('data/demo_taxonomy.json')
manager = ConversationManager(MockLLMClient(), taxonomy)
first = manager.start_session('session-1')
response = manager.handle_user_turn('session-1', 'می‌خواهم تحلیلگر داده شوم')
print(response.message, response.is_complete, response.profile_json)
```

این متدها synchronous هستند. در سرویس async آن‌ها را در worker thread اجرا کنید. یک manager به‌ازای نشست مرورگر در UI نمونه ساخته می‌شود و در cache سراسری قرار ندارد. اگر سرویس مشترک ساخته می‌شود، مالکیت session_id باید در لایهٔ احراز هویت کنترل شود. این کتابخانه با session_id به‌تنهایی احراز هویت نمی‌کند.

متدهای تکمیلی:

- `start_session(session_id)`: سؤال اول. در حالت عادی پیش از اولین پیام صدا زده شود.
- `handle_user_turn(session_id, user_text)`: پاسخ، استخراج، اصلاح و تأیید.
- `apply_profile_update(session_id, ProfileEdit | dict)`: اصلاح اتمیک فرم؛ نقش/مهارت نامعتبر رد می‌شود و پروفایل قبلی حفظ می‌شود.
- `confirm_profile(session_id)`: تأیید صریح فرم؛ بدون API؛ تنها با تکمیل فیلدهای ضروری موفق است.
- `reset_session(session_id)`: پاک‌کردن حافظهٔ این نشست.

## معناهای TurnResponse

سه فیلد اصلی قرارداد دقیقاً `message`, `is_complete`, `profile_json` هستند. `bot_message` صرفاً property سازگاری پایتون است و در JSON صادر نمی‌شود.

| فیلد | معنا |
|---|---|
| schema_version | نسخهٔ قرارداد: 1.0 |
| is_complete | اطلاعات ضروری موجود است و کاربر پروفایل فعلی را تأیید کرده؛ برابر با «بودجهٔ سؤال تمام شد» نیست |
| status | collecting / awaiting_confirmation / complete / incomplete / error |
| question_count | شمار سؤال‌های ارزیابی تولیدشده، حداکثر ۶ |
| turn_count | شمار پیام‌های ارزیابی پذیرفته‌شده، سقف ۶؛ اصلاح‌های بعدی آن را افزایش نمی‌دهند |
| assessment_finished | ارزیابی پرسشی تمام شده؛ الزاماً پروفایل آماده نیست |
| profile_revision | با تغییر واقعی داده‌ها افزایش می‌یابد؛ تأیید تنها، دادهٔ پروفایل را تغییر نمی‌دهد |
| warnings | فقط کدهای ثابت؛ متن ورودی و مفهوم نامعتبر را افشا نمی‌کند |
| roadmap / summary | هر دو مربوط به دادهٔ جاری‌اند؛ هنگام تغییر یا خطای گراف null هستند |
| usage | شمار تماس‌ها، خطاها، توکن‌های گزارش‌شده، بودجه، مصرف نامشخص و هزینهٔ اختیاری |

`is_complete=true` به‌معنای تکمیل پروفایل است. اگر موتور گراف خطا بدهد، این فیلد ممکن است true باشد ولی `roadmap=null` و هشدار `graph_error` صادر شود؛ UI باید آماده‌بودن گراف را جدا بررسی کند.

پروفایل عمومی شامل target_role، target_level، current_level، education، experience_years، known_concepts و is_confirmed است. `skills_assessed` فقط در وضعیت داخلی است: آرایهٔ خالی اگر همراه با پاسخ صریح «هیچ مهارتی ندارم» باشد معتبر است. داده‌های حذف‌شدهٔ نامعتبر به پروفایل عمومی نشت نمی‌کنند.

## قرارداد تاکسونومی

مرجع دقیق: `taxonomy.schema.json` و نمونهٔ `../data/demo_taxonomy.json`.

- شناسه‌ها انگلیسی، کوچک و شامل حروف/عدد/underscore هستند.
- `roles`: آرایهٔ اشیا با id، label، domain، aliases، requirements.
- `requirements`: سه کلید junior/mid/senior و فهرست صریح مفاهیم هر سطح. موتور سطح‌های پایین را خودکار به بالاتر اضافه نمی‌کند؛ فایل باید اجتماع موردنیاز را تعریف کرده باشد.
- `concepts`: آرایهٔ اشیا با id، label، aliases، prerequisites.
- تمام مراجع باید موجود و گراف بدون چرخه باشد. alias مشترک بین دو شناسه رد می‌شود.
- aliases فایل خوانده می‌شوند؛ تطبیق نقش دقیق و پس از یکسان‌سازی فاصله/نیم‌فاصله است. جستجوی آزاد زیررشته‌ای وجود ندارد.
- `is_demo=true` برای نمونه و false برای دادهٔ تیم است. تغییر دادهٔ گراف باید با تغییر version همراه باشد.
- خطای فایل یا نبود آن، توقف پیکربندی ایجاد می‌کند؛ هیچ fallback پنهان به Mock وجود ندارد.
- حداقل ۱۰ نقش در سه حوزه، مسئولیت آماده‌سازی تاکسونومی نهایی تیم است؛ فایل نمونه ۱۲ نقش در سه حوزه دارد. validator فایل کوچک‌تر را برای توسعه می‌پذیرد و به‌تنهایی گواهی انطباق A-02 نیست.

## قرارداد GraphEngine

```python
class TeamGraphAdapter:
    def __init__(self, taxonomy):
        self.taxonomy = taxonomy

    def build_roadmap(self, profile, revision):
        # Call team's deterministic graph engine here.
        # Return dialogue.schemas.Roadmap, not prose.
        ...

manager = ConversationManager(client, taxonomy,
                              graph_engine=TeamGraphAdapter(taxonomy))
```

فرمول گره‌های قابل‌نمایش:

`closure(required(target_role, target_level)) - set(profile.known_concepts)`

معنای یال: source پیش‌نیاز target است. فقط یال‌هایی که هر دو سرشان در مفاهیم باقی‌مانده‌اند صادر می‌شوند. پیش‌نیازِ ازقبل‌دانسته‌شده دوباره در گراف باقی‌مانده قرار نمی‌گیرد؛ سایر پیش‌نیازهای نادانسته همچنان حضور دارند.

خروجی باید schema_version، taxonomy_version، profile_revision، profile_fingerprint، target_role، target_level، nodes، edges و study_order داشته باشد. fingerprint با `dialogue.graph.fingerprint(profile)` ساخته می‌شود و فیلد تأیید را وارد هش نمی‌کند. ترتیب شناسه‌های مهارت‌ها در محاسبهٔ آن مرتب می‌شود.

validator تمام این موارد را بررسی می‌کند: نسخه و revision، هش پروفایل، مجموعهٔ دقیق گره‌های موردانتظار، یال‌های دقیق ناشی از تاکسونومی، labelهای مرجع، عدم تکرار، ترتیب توپولوژیک و نبود گرهٔ ساختگی. موتور تیم باید ترتیب معتبر تولید کند؛ ترتیب‌های توپولوژیک متفاوت می‌توانند معتبر باشند.

موتور گراف هنگام تأیید پروفایل فراخوانی می‌شود. بعد از اصلاح، پروفایل جدید تأیید و سپس خروجی جدید ساخته می‌شود؛ نمایش خروجی قدیمی ممنوع است. اگر خود موتور تیم async است، آداپتر sync مناسب لایهٔ سرویس فراهم کنید.

## تسک ۵ / A-09

از قالب قطعی استفاده شده تا متن فقط اطلاعاتی را توضیح دهد که در گراف دیده می‌شود: تعداد مفاهیم، فهرست labelها با study_order و روابط پیش‌نیاز. هیچ LLM دیگری برای خلاصه فراخوانی نمی‌شود. گراف تهی، پیام «مفهومی باقی نمانده» می‌دهد. هزینه، زمان یادگیری، توضیح شغلی و URL خارج از قرارداد ساخته نمی‌شود.

## خطا و حریم خصوصی

مدل می‌تواند دادهٔ ناقص بدهد، درخواست را رد کند یا timeout داشته باشد. در این حالات داده‌های قبلی حفظ می‌شوند و خطا خام چاپ نمی‌شود. مصرف همان درخواست، حتی با خروجی بدشکل، در صورت گزارش درگاه ثبت می‌شود. ۴۰۰ بدون retry خودکار برمی‌گردد. اعتبارسنجی schema و شاهد مهارت مکمل هم‌اند؛ نامِ معتبرِ یک مهارت دلیل بلدبودن کاربر نیست.

نمونهٔ کامل JSON خروجی در `example_turn_response.json` است و با گفتگوی مصنوعی تولید شده است. JSON Schemaهای استخراج و پاسخ نیز کنار آن موجودند.

## انتخاب پروتکل اتصال مدل — نسخهٔ ۱٫۰٫۱

`LLMSettings(protocol="openai")` پیش‌فرض قبلی را حفظ می‌کند. `protocol="gemini"` برای native Gemini است: `OPENAI_BASE_URL=https://api.metisai.ir`، مسیر generateContent و هدر x-goog-api-key. response_format=json_object به responseMimeType=application/json و json_schema به responseJsonSchema نگاشت می‌شود؛ prompt_json فقط از دستور JSON استفاده می‌کند. پاسخ candidates/parts و usageMetadata پیش از Pydantic به قرارداد مشترک تبدیل می‌شود؛ متن thinking جزو JSON پروفایل محسوب نمی‌شود ولی توکن آن به مصرف خروجی اضافه می‌شود.
