# خريطة منطق مشروع Kurmanji-TTS — Project Logic Map

> أُنشئت في 2026-11-18 من شجرة العمل الحالية في `C:\Users\Luqman\Desktop\Projecton\kurmanji-tts`.
>Stack: Python 3.13 (`.build-venv`) / Flet 0.86.5 / PyInstaller / Piper VITS CLI / sherpa-onnx 2.0.1 / ONNX Runtime.
>Platforms: Windows 11 (سطح المكتب)؛ Linux مدعوم جزئياً عبر `aplay`. لا يوجد هدف جوال بعد.
>نمط الدليل: كل ادعاء ينتهي بدليل `file:line`. الحالات: **مُلاحظ (OBSERVED)** = قرأتُ الكود أو شغّلته، **مُستنتج (INFERRED)** = قراءة عقلانية لكود تم تتبّعه، **غير متحقق (UNVERIFIED)** = مذكور في توثيق أو مُستنتج من وصف وليس مؤكداً بالكود.
>تشغيل التطبيق: شغّلتُ `dist\Kurmanji-TTS.exe` وتحققتُ أنه يبقى حياً 6 ثوانٍ (OBSERVED)، لكنني **لم أُدرِ مسار التشغيل الأول في الواجهة تفاعلياً**؛ لذلك القسم 5 و6 مُستنتجان من الكود الذي تتبّعتُه، لا من ملاحظة شاشة فعلية.

---

## 0. TL;DR

Kurmanji-TTS هو تطبيق سطح مكتب عربي الواجهة يحويل نص الكورمانجي (أبجدية Hawar اللاتينية) والعربية الفصحى إلى كلام محلياً على المعالج دون إنترنت. جمهوره طلاب وباحثون يحتاجون صوتاً كورمانجياً دون خدمة سحابية. النشاط الأساسي: كتابة نص → اختيار محرك → توليد WAV → الاستماع داخلياً أو الحفظ.

- **أول ما يراه المستخدم الجديد:** نافذة Flet بعنوان `Kurmanji-TTS` ورسالة `جاري فحص النموذج...` ثم `النموذج جاهز` (`main.py:78`, `locales.py:17-18`).
- **أول قرار عليه اتخاذه:** اختيار `محرك النطق` من ثلاثة خيارات (`locales.py:32-36`, `main.py:279`).
- **أول قيمة حقيقية:** الضغط على `توليد الصوت` فيظهر ملف WAV ومؤشرات `زمن التوليد` و`RTF` (`main.py:44-48`, `main.py:555`).
- **الحلقة التي تُبقي المستخدم:** تكرار تعديل السرعة/المتحدث/النص ثم التوليد والاستماع؛ لا توجد حسابات أو نقاط أو streaks.
- **أكبر تحفظ اليوم:** نماذج Meta MMS مرخّصة `CC-BY-NC 4.0`، وREADME ما زال يصف نسخة Piper فقط و9 اختبارات (انظر القسم 13).

---

## 1. ما هذا المشروع؟

| | |
| :--- | :--- |
| الغرض | تحويل نص Hawar الكورمانجي والعربية الفصحى إلى كلام WAV على CPU دون شبكة (`main.py:3`, `setup_runtime.py:5`). |
| الجمهور | مستخدم عربي الواجهة يقرأ/يكتب الكورمانجية أو العربية؛ ثلاث لغات واجهة: `ar` و`ku` و`en` (`locales.py:11`). |
| المنصات | Windows أساساً عبر `winmm/MCI`؛ Linux عبر `aplay` (`audio_player.py:152`, `audio_player.py:271`). لا يوجد Android/iOS بعد. |
| المحتوى | نماذج محلية: `model.onnx` (Piper، 90 متحدثاً) + `mms_kmr/model.onnx` + `mms_ara/model.onnx`، وكلها تُجلب مرة واحدة (`config.py:22-24`, `setup_runtime.py:51`). |
| الدخل | لا يوجد (لا إعلانات ولا اشتراك). |
| مؤشر النضج | الإصدار `1.0.0` (`config.py:20`)، 34 اختباراً آلياً (`tests/test_kurmanji_tts.py`، عدد دوال `test_` = 34)، ملف تنفيذي 67,839,141 بايت. |

---

## 2. كيف تشغّله؟

| الأمر | ماذا يفعل | ملاحظة |
| :--- | :--- | :--- |
| `python -m venv .venv` + `pip install -r requirements.txt` | يهيّئ بيئة MSYS2 للمشروع | `.venv` لا يستطيع تحميل wheel الخاص بـ sherpa-onnx (محاولة تثبيت فشلت: source build → `Failed to configure sherpa-onnx`). |
| `python setup_runtime.py` | ينزّل Piper و`model.onnx` ونموذجي `mms_kmr`/`mms_ara` وينسخ `models/` إلى `dist/models/` | يتخطّى الملفات الموجودة (`setup_runtime.py:156-181`, `setup_runtime.py:197-205`). |
| `python main.py` | يشغّل واجهة Flet (`main.py:1012-1013`) | يحتاج الملفات السابقة موجودة محلياً. |
| `python tests\test_kurmanji_tts.py` | 34 اختبار وحدة/تكامل | يستخدم `tests/mock_piper.py`، ولا يحتاج نماذج حقيقية. |
| `python tests\real_engine_smoke.py` | اختبار Piper الحقيقي + وضعي MMS | يحتاج `.build-venv` لاستيراد sherpa-onnx. |
| `scripts\build_windows.bat` | يبني `dist\Kurmanji-TTS.exe` | يفضّل `.build-venv` إن وُجد ويضيف ملفات sherpa الثنائية (`scripts/build_windows.bat:5-11`, `:26-31`, `:34-36`). |

**البيئة:** لا متغيّرات مطلوبة للمستخدم. سكربت البناء يضبط `SSL_CERT_FILE` من certifi تلقائياً (`scripts/build_windows.bat:20-24`).
**محاكاة تثبيت نظيف:** احذف `%APPDATA%\kurmanji-tts\settings.json` (`config.py:35-44`, `config.py:165`) وأعد تشغيل `main.py`؛ يعود `engine_profile` إلى `piper_kmr` (`config.py:136`, `config.py:159-160`).

---

## 3. كيف يعمل؟

**تسلسل الإقلاع (بداية نظيفة):**

1. `ft.run(main)` يستدعي الدالة `main(page)` — `main.py:1012-1013`.
2. `AppSettings.load()` يقرأ `%APPDATA%\kurmanji-tts\settings.json` أو يعيد الإعدادات الافتراضية — `main.py:80`, `config.py:163-166`.
3. يُحدَّث `model_path` ليطابق `engine_profile` المحفوظ — `main.py:84-92`, `config.py:65-70`.
4. يُنشأ `UnifiedTTSEngine` بثلاثة محركات داخلية — `main.py:101`, `tts_engine.py:713-742`.
5. `page.rtl` يُضبط من `ui_language` — `main.py:100`، ثم تُبنى البطاقات الأربع — `main.py:1000-1005`.
6. `refresh_profile_ui()` ثم `refresh_engine_status()` ثم `page.update()` — `main.py:1007-1009`.

**طبقات النظام:**

| الطبقة | المكان | المسؤولية |
| :--- | :--- | :--- |
| الواجهة | `main.py` | Flet controls، مؤشرات، إعدادات، أحداث (`main.py:227`, `main.py:266`, `main.py:279`). |
| التوجيه | `tts_engine.py` | `UnifiedTTSEngine.set_profile` يختار المحرك (`tts_engine.py:751-759`). |
| المحركات | `tts_engine.py` | `KurmanjiTTSEngine` (Piper) و`SherpaMMSEngine` (MMS) (`tts_engine.py:200`, `tts_engine.py:565`). |
| النص | `text_utils.py` | NFC، أرقام، قاموس، تصفية توكنات (`text_utils.py:68`, `text_utils.py:270`, `text_utils.py:337`). |
| الصوت | `audio_player.py` | MCI/aplay، إدارة ملفات WAV المؤقتة (`audio_player.py:152`, `audio_player.py:396`). |
| الإعدادات | `config.py` | `AppSettings`، مسارات النماذج، `settings_version=4` (`config.py:122-137`). |
| التجهيز | `setup_runtime.py` | تنزيل ومزامنة `dist/models` (`setup_runtime.py:197-205`). |
| الترجمة | `locales.py` | ثلاث لغات واجهة واتجاه RTL (`locales.py:11-12`, `locales.py:15-64`). |

**لماذا لا تتغير الواجهة عند إضافة محرك؟** لأن `EngineStatus` و`SynthesisResult` هما عقد مشترك، و`UnifiedTTSEngine.synthesize` يمرّر الاستدعاء إلى `self.engine.synthesize` بلا أي معرفة بنوع المحرك (`tts_engine.py:48`, `tts_engine.py:62`, `tts_engine.py:779-794`).

---

## 4. العمود الفقري للبيانات والحالة

| المفتاح/المخزن | مَن يكتبه | مَن يقرأه | الشكل | مَن يمسحه |
| :--- | :--- | :--- | :--- | :--- |
| `%APPDATA%\kurmanji-tts\settings.json` | `AppSettings.save` (`config.py:215-220`) | `AppSettings.load` (`config.py:163`) | JSON و13 حقلًا أهمها `engine_profile`, `model_path`, `ui_language` (`config.py:125-137`) | المستخدم يدوياً |
| `models/model.onnx` + `.json` | `setup_runtime.install_kurmanji_model` (`setup_runtime.py:111`) | `KurmanjiTTSEngine.check_status` (`tts_engine.py:248`) | أوزان Piper + ميتاداتا 90 متحدثاً | لا أحد |
| `models/mms_kmr/{model.onnx,tokens.txt}` | `setup_runtime.install_mms_model` (`setup_runtime.py:156`) | `SherpaMMSEngine.check_status` (`tts_engine.py:581`) | ONNX + أبجدية Hawar | لا أحد |
| `models/mms_ara/{model.onnx,tokens.txt,config.json}` | نفسه | نفسه | ONNX + أبجدية عربية | لا أحد |
| `models/pronunciation_dict.json` | `text_utils._load_pronunciation_dict` عند الغياب (`text_utils.py:245`) | `prepare_text_for_tts` (`text_utils.py:270`) | `{"TTS": "tî tî es", ...}` | المستخدم يدوياً |
| `models/speaker_metadata.json` | ثابت في الحزمة | `parse_model_metadata` (`tts_engine.py:73`) | قائمة أسماء متحدثين | لا أحد |
| WAV مؤقت داخل جلسة التشغيل | `AudioSessionManager` (`audio_player.py:80`) | `InAppAudioPlayer` (`audio_player.py:396`) | ملفات PCM 16-bit | `audio_session.shutdown()` (`main.py:996`) |

- **السجل المركزي:** `AppSettings` (13 حقلًا)، لا يوجد كائن مستخدم/تقدّم.
- **السحابة:** لا توجد. كل شيء محلي، والوحيد الذي يلمس الشبكة هو `setup_runtime.py` مرة واحدة فقط عند التجهيز.
- **المزامنة:** `copy_models_to_dist` ينسخ مجلدات `models/` إلى `dist/models/` بعد التنزيل (`setup_runtime.py:181`). لا يوجد conflict handling لأن لا كتابة بعد التثبيت.
- **القواعد الأمنية:** لا توجد قواعد خادم؛ العزل هو عزل عملية Piper عبر `subprocess` فقط (`tts_engine.py:322-345`).

---

## 5. التشغيل الأول: ماذا يرى المستخدم بالترتيب؟

> **مُستنتج (INFERRED)** من الكود؛ لم أُدرِ الواجهة تفاعلياً.

| # | اللحظة | ما يظهر | ما يجب أن يفعله المستخدم | الدليل |
| :- | :--- | :--- | :--- | :--- |
| T0 | فتح exe | نافذة 920×760، الوضع الداكن افتراضياً | لا شيء | `main.py:103-108`, `config.py:131` |
| T1 | بعد `page.add` | شريط علوي فيه `Kurmanji-TTS` وحالة `جاري فحص النموذج...` وبطاقات: أمثلة، حقل النص، المحرك/المتحدث/السرعة، المشغّل | ينتظر فحص النموذج | `main.py:1000-1009`, `locales.py:16-18` |
| T2 | بعد `refresh_engine_status` | تتغير الحالة إلى `النموذج جاهز (22050 Hz | 90 متحدث)` ويُنشأ `Speaker 54` | يقرأ الحالة | `main.py:532-548`, `locales.py:18` |
| T3 | أول قرار | قائمة `محرك النطق` فيها `Kurmancî — Piper (90 Speakers)` و`Kurmancî — Meta MMS` و`العربية — Meta MMS` | يختار محركاً | `main.py:279-287`, `locales.py:32-36` |
| T4 | بعد الاختيار | يتغير اتجاه الحقل والأمثلة؛ قائمة المتحدثين تُعطَّل مع MMS | يلاحظ التغيير | `main.py:291-317`, `main.py:814-830` |

**البوابة بكلمات بسيطة:** لا توجد شاشة onboarding ولا تسجيل ولا صلاحيات. البوابة الوحيدة هي `engine_profile` في الإعدادات؛ قيمته الافتراضية `piper_kmr` (`config.py:136`). لا يوجد tour ولا coachmarks ولا "تم رؤية من قبل" (`UNVERIFIED` بعد البحث: لم يُعثر على `hasSeen`/`onboarding` في الكود).

---

## 6. الجلسة الأولى: ماذا تفعل خطوة بخطوة؟

1. اكتب أو الصق نصاً في الحقل — يظهر عدّاد `الأحرف:` و`الكلمات:` و`حروف Hawar المكتشفة:` مباشرة (`main.py:227-244`, `locales.py:21-23`).
2. أو اضغط إحدى الرقائق تحت `أمثلة نصية سريعة:` فيُملأ الحقل (`main.py:246-264`, `locales.py:24`).
3. اختر `محرك النطق` — يُكتب `engine_profile` في `settings.json` ويُبدَّل المسار والمتحدث (`main.py:814-830`).
4. اختر `المتحدث` مع Piper فقط — القائمة من `meta.speakers` والافتراضي `Speaker 54` (`main.py:532-548`, `tts_engine.py:146-150`).
5. اضبط `السرعة:` من 0.50x إلى 1.50x — تُحفظ في `settings.json` وتُترجم داخلياً إلى `length_scale = 1/speed` (`config.py:139-142`, `main.py:320-332`).
6. اضغط `توليد الصوت` — يُنشأ WAV، وتظهر `زمن التوليد:` و`مدة الصوت:` و`RTF:` و`التردد:` (`main.py:555-614`, `locales.py:44`, `locales.py:49-53`).
7. اضغط `تشغيل` / `إيقاف مؤقت` / `إيقاف` للاستماع داخل التطبيق، أو `حفظ WAV` للتصدير (`main.py:268-278`).

**اللحظة الفارقة (aha):** ظهور مؤشرات `RTF` ومدة الصوت بعد التوليد مباشرة (`main.py:599-611`).
**إذا بدا التطبيق "مُعدّاً مسبقاً":** احذف `settings.json` من `%APPDATA%\kurmanji-tts` وأعد التشغيل ليعود `piper_kmr`.
**أقصر طريق للقيمة:**_example chip → `توليد الصوت` → `تشغيل`.

---

## 7. كل الشاشات

هذا التطبيق **لا يملك router**؛ شاشته واحدة تتكوّن من أربع بطاقات. عدد المسارات في router = 0، عدد الصفحات في هذا الجدول = 4 بطاقات + حواران.

| الشاشة/القسم | الملف | الغرض | كيف يصل إليها المستخدم | الحواجز |
| :--- | :--- | :--- | :--- | :--- |
| الشريط العلوي | `main.py:783-804` | الحالة + لغة الواجهة + الإعدادات + الثيم | دائماً ظاهر | لا شيء |
| بطاقة الإدخال | `main.py:919-942` | أمثلة + حقل النص + العدّادات | دائماً ظاهرة | تحقق 5,000 حرف (`text_utils.py:117`) |
| بطاقة التحكم | `main.py:944-963` | محرك النطق + المتحدث + السرعة + التوليد | دائماً ظاهرة | المتحدث معطّل مع MMS (`main.py:305-313`) |
| بطاقة المشغّل | `main.py:965-987` | تشغيل/إيقاف/موضع + مقاييس + حفظ | بعد توليد أول WAV | الأزرار معطّلة قبل Generate (`main.py:268-278`) |
| حوار الإعدادات | `main.py:632-708` | مسارات النموذج وPiper والمثابرة | زر `⚙` (`main.py:711-719`) | لا شيء |
| شريط تنبيه الخطأ | `main.py:117-150` | رسائل مثل `النموذج أو المحرك غير جاهز` | عند فشل | يختفي بعد الإغلاق |

---

## 8. خريطة التنقل

```
نافذة Kurmanji-TTS
├── Header: حالة النموذج | لغة الواجهة | ⚙ الإعدادات | الثيم
├── input_card: أمثلة سريعة → text_input → العدّادات
├── controls_card: محرك النطق → المتحدث → السرعة → توليد الصوت
└── player_card: تشغيل | إيقاف مؤقت | إيقاف | شريط التقدم | المقاييس | حفظ WAV
```

لا توجد مسارات غير قابلة للوصول، ولا عناصر تنقل تؤدي إلى placeholders. لا يوجد BottomNav أو Drawer.

---

## 9. الحلقات

- **حلقة اليوم الأول:** اختيار محرك → كتابة/_example → توليد → استماع → تعديل السرعة/المتحدث → إعادة التوليد (`main.py:555`, `main.py:320`).
- **حلقة يومية:** لا توجد حوافز أو slate؛ المستخدم يعود حين يحتاج صوتاً لنص جديد. لا يوجد تخزين سجل المخرجات بعد إغلاق التطبيق (WAV مؤقت).
- **حلقة طويلة الأمد:** لا توجد مستويات أو unlocks؛ التوسع الوحيد المخطط هو نقل المنطق إلى الجوال (`docs/Kurmanji-TTS_Graduation_Report.docx`، الفصل 7).

| الفعل | المكافأة | العتبة/المصدر |
| :--- | :--- | :--- |
| تغيير السرعة | صوت أسرع/أبطأ فوراً | `0.50–1.50` (`config.py:150`) |
| تبديل المحرك | جودة أعلى أو سرعة أعلى | `ENGINE_PROFILES` (`config.py:25`) |
| توليد نص | ملف WAV + RTF | `main.py:599-611` |

**نقطة الانكسار:** إن لم تكن النماذج قد جُمعت محلياً، تظهر `النموذج أو المحرك غير جاهز` وتتوقف الحلقة حتى تشغيل `setup_runtime.py` (`main.py:474`, `locales.py:19`).

---

## 10. الشخصيات والفروع

| الشخصية | الشاشة الأولى | الفرق | الدليل |
| :--- | :--- | :--- | :--- |
| جديد، `piper_kmr` | كما T0–T4 | قائمة 90 متحدثاً، حقل LTR، أمثلة كورمانجية | `config.py:136`, `text_utils.py:22` |
| جديد، `mms_kmr` | نفس الشاشة | متحدث واحد `MMS Speaker 0`، حقل LTR، بلا eSpeak | `locales.py:37`, `main.py:305-313` |
| جديد، `mms_ara` | نفس الشاشة | متحدث `MMS Arabic`، حقل RTL، أمثلة عربية | `locales.py:36`, `locales.py:38`, `main.py:291-296` |
| عائد | يستعيد `engine_profile` و`ui_language` من `settings.json` | لا يعيد الاختيار | `config.py:163-166` |
| بدون إنترنت | يعمل كاملاً بعد التثبيت | لا يوجد مؤشر اتصال في الواجهة | `setup_runtime.py:197-205` |
| واجهة عربية/كوردية/إنجليزية | نفس البطاقات بترجمات مختلفة | `page.rtl` يتغير مع `ar` فقط | `main.py:100`, `locales.py:11-12` |

---

## 11. البوابات والأشياء المخفية

| الشيء | المفتاح/الموضع | الافتراضي | أثر الإيقاف | الدليل |
| :--- | :--- | :--- | :--- | :--- |
| العملية الدافئة | `use_persistent_process` | `True` | يعود إلى استدعاء Piper منفرد أبطأ | `config.py:132`, `tts_engine.py:490-521` |
| وضع MMS | `engine_profile` | `piper_kmr` | يختفي محركا Meta MMS من الاستخدام | `config.py:136` |
| زر التبديل الصوتي | `speaker_dropdown.disabled` | `False` مع Piper | يُعطَّل مع MMS | `main.py:305-313` |
| الإعدادات المتقدمة | حوار `⚙` | مخفي خلف الزر | لا شيء | `main.py:632-719` |
| نموذج Kareem القديم | — | **محذوف** | استُبدل بـ `mms_ara` | `setup_runtime.py:51`, `THIRD-PARTY-LICENSES.md:28-34` |

---

## 12. الحالات الحدّية وسلوك الفشل

- **نص فارغ/رموز فقط:** `validate_kurmanji_input` يرجع `False` مع `يرجى إدخال نص كورمانجي أولاً` أو `النص يحتوي على رموز فقط` (`text_utils.py:117-135`, `locales.py:82-84`).
- **نص أطول من 5,000 حرف:** رسالة `النص طويل جداً` (`config.py:133`, `locales.py:83`).
- **نموذج مفقود:** `EngineStatus(ready=False)` ورسالة `النموذج أو المحرك غير جاهز` + تلميح `engine_hint` (`main.py:470-474`).
- **sherpa غير مثبت:** `err_sherpa_missing` (`tts_engine.py:595-605`, `locales.py:39`).
- **فشل العملية الدافئة:** يعود تلقائياً إلى one-shot دون إظهار خطأ للمستخدم (`tts_engine.py:497-521`).
- **WAV تالف/صامت:** `verify_wav_file` يرمي `TTSEngineError` (`tts_engine.py:179-197`).
- **إغلاق التطبيق:** يُغلق المشغّل والمحرك ويُنظَّف WAV (`main.py:992-998`).
- **لا يوجد 404** لأن لا مسارات؛ لا يوجد error boundary لأن لا React.

---

## 13. الفجوات التي يعترف بها الكود/التوثيق

- `README.md:5` يقول «جميع الاختبارات (9/9) نجحت» بينما الكود يحتوي 34 اختباراً (`tests/test_kurmanji_tts.py`) — **تضارب توثيق**.
- `README.md:28-31` يذكر Piper فقط ولا يذكر `mms_kmr`/`mms_ara` أو sherpa-onnx أو `.build-venv` — **تضارب توثيق**.
- `README.md:131` يقول إن التطبيق يفتح الملف في مشغل النظام عند غياب حزم Linux؛ بينما الكود يستخدم `aplay` فقط ولا يحتوي `os.startfile`/`xdg-open` (`audio_player.py:271-306`, اختبار `test_no_external_player_symbols_in_source`).
- `settings_version` ما زال 4 رغم حقل `engine_profile` الجديد؛ الترحيل يعتمد على `if "engine_profile" not in raw` لا على رقم إصدار (`config.py:199-203`, `config.py:137`). يعمل، لكنه هش.
- لا تقييم MOS بشري؛ مُذكور صراحة كخارج النطاق في التقرير (الفصل 1/5).
- لم يُعثر على TODO ids أو Known Gaps داخل الكود نفسه.

---

## 14. الدليل والأسئلة المفتوحة

| الادعاء | الحالة | الدليل |
| :--- | :--- | :--- |
| ثلاثة أوضاع محرك موحّدة العقد | OBSERVED | `config.py:25`, `tts_engine.py:713-794` |
| Piper يعمل بعملية دافئة `--json-input` | OBSERVED | `tts_engine.py:306-345`, `tts_engine.py:398` |
| MMS يُبقى في RAM | OBSERVED | `tts_engine.py:581-649` (`self._tts` يُنشأ مرة ويُغلق عند التبديل `tts_engine.py:751-759`) |
| NFC وحروف Hawar | OBSERVED | `text_utils.py:68-76`, `text_utils.py:22` |
| تصفية توكنات MMS | OBSERVED | `text_utils.py:319-359`, `text_utils.py:337` |
| مشغّل MCI/aplay | OBSERVED | `audio_player.py:152`, `audio_player.py:271` |
| 34 اختباراً | OBSERVED | عدّ `def test_` = 34؛ التشغيل انتهى بـ `OK` |
| الملف التنفيذي يعمل دون إنترنت | OBSERVED (جزئي) | شغّلته وبقي حياً 6s؛ واختبار probe داخل exe نجح بتوليد WAV من `dist/models` |
| ترتيب الشاشة الأول للمستخدم | INFERRED | `main.py:1000-1009` + `locales.py:16-18`؛ لم أُدرِ الواجهة تفاعلياً |
| README يصف الإصدار الحالي | UNVERIFIED / متناقض | `README.md:5`, `:28-31`, `:131` |

**UNVERIFIED / أسئلة تحتاج إجابة بشرية:**
- هل يجب رفع `settings_version` إلى 5 وترحيل `tts_language → engine_profile` رسمياً؟
- هل يُسمح بالاستخدام التجاري لنماذج Meta MMS في سياق المشروع؟ الترخيص `CC-BY-NC 4.0` يقول لا (`THIRD-PARTY-LICENSES.md:13`).
- هل سكربت `scripts/build_linux.sh` ما زال متوافقاً مع sherpa-onnx؟ لم يُشغّل في هذه المراجعة.
- أين تُحفظ نية التوسع إلى Android/iOS؟ في التقرير فقط، لا في الكود.

---

## 15. قواعد كتابة الكود وقراءته (للذكاء الاصطناعي القادم)

> هذه قواعد عملية مستنتجة من البنية الحالية، وليست ادعاءات عن سلوك موجود.

1. **لا تضع منطق محرك داخل `main.py`.** أي محرك جديد يُضاف ككلاس في `tts_engine.py` ويُسجَّل في `UnifiedTTSEngine` (`tts_engine.py:713`). الواجهة لا تعرف سوى `check_status()` و`synthesize()`.
2. **لا تغيّر عقد الإرجاع أبداً.** كل محرك يجب أن يُرجع `EngineStatus` و`SynthesisResult` نفس الحقول (`tts_engine.py:48`, `tts_engine.py:62`). هذا هو السبب الذي جعل إضافة MMS بلا إعادة كتابة للواجهة.
3. **سجّل أي نموذج جديد في أربعة أماكن معاً:** ثوابت المسارات في `config.py:22-25`، `ENGINE_PROFILES`، `setup_runtime.MMS_MODELS` (`setup_runtime.py:51`)، وتسميات `locales.py:32-38`. نسيان واحد منها ينتج واجهة بلا محرك أو محرك بلا تنزيل.
4. **الملفات داخل `models/<profile>/` فقط.** نماذج MMS لا تُوضع في جذر `models/` لأن `discover_default_model` يفترض أن `model.onnx` هو نموذج Piper (`config.py:47-56`).
5. **واضح المعنى:** ابدأ كل دالة أو كلاس جديد بـ docstring عربي قصير يشرح *لماذا* يوجد، ثم سطر إنجليزي يشرح *ماذا* يفعل. مثال: `"""يُبقي النموذج في الذاكرة لتجنّب إعادة التحميل. Keeps the ONNX model warm in RAM."""`.
6. **لا أرقام سحرية.** عرّف ثابتاً أعلى الملف لأي قيمة تتكرر (مثل `25 ms` polling أو 5,000 حرف). القيم الموجودة حالياً في `tts_engine.py:398` و`config.py:133` هي المرجع.
7. **أسماء صريحة بوحداتها:** استخدم `length_scale`, `sample_rate`, `generation_time_seconds`, `max_text_length` — لا تختصر إلى `ls` أو `sr` إلا داخل نطاق 3 أسطر.
8. **التحقق من WAV إلزامي.** لا تفترض أن Piper أو sherpa أنتج ملفاً صالحاً؛ مرّر كل مخرج عبر `verify_wav_file` (`tts_engine.py:179`) قبل إرجاع النتيجة.
9. **عزل LTR في النصوص العربية:** في DOCX استخدم LRM/RLM حول الرموز اللاتينية مع NBSP عند الحاجة (كما في مولّد التقرير)، ولا تستخدم FSI/PDI في PPTX لأن PowerPoint يعرضها كربعات؛ استخدم تقسيمRuns حسب النص كما في `deck_lib`. اترك أرقام الأقسام في العناوين غير معزولة حتى يظهر الفراغ بعدها.
10. **الترجمة ليست تجميلاً.** أي نص يراه المستخدم يجب أن يمر عبر `tr(current_lang, key)` (`main.py:82-84`, `locales.py`) ويُضاف بنفس المفتاح إلى اللغات الثلاث؛ اختبار `test_all_languages_have_identical_complete_keys` يفشل إن نسيتَ واحدة (`tests/test_kurmanji_tts.py`).
11. **لا مشغّل خارجي.** لا تضف `os.startfile` أو `xdg-open` أو `flet_audio`؛ المشغّل الداخلي إلزامي (`audio_player.py:396`, اختبار `test_no_external_player_symbols_in_source`).
12. **أي تغيير في `text_utils` أو `tts_engine` يحتاج اختباراً** في `tests/test_kurmanji_tts.py`، ثم شغّل `python tests\test_kurmanji_tts.py` وتأكد أن العدد 34 أو أكثر و`OK`.
13. **التراخيص جزء من الكود.** عند إضافة مكوّن، حدّث `THIRD-PARTY-LICENSES.md` في نفس التغيير، واذكر اسم الترخيص وطريقة العزل (عملية منفصلة أم مكتبة مدمجة).
14. **README ليس مصدر الحقيقة.** إن اختلف مع الكود، صدّق الكود وسجّل الاختلاف في القسم 13 بدل تركه سبباً للارتباك لدى القارئ القادم.
15. **عند بناء exe استخدم `.build-venv`** لا `.venv`، لأن wheel الخاص بـ sherpa-onnx لا يعمل مع MSYS2 Python؛ السكربت يتولى ذلك تلقائياً (`scripts/build_windows.bat:5-11`).

---

### ملخص للقارئ القادم (4–6 أسطر)

- التطبيق محوّل نص إلى كلام، محلي 100%، بثلاثة أوضاع محرك بواجهة واحدة.
- التشغيل الأول لا يعرض onboarding؛ أول قرار هو اختيار `محرك النطق`.
- هذه الخريطة في `docs\PROJECT_LOGIC.md`؛ الدليل التفصيلي في `docs\Kurmanji-TTS_Graduation_Report.docx`.
- ما يناقض التوثيق: README يقول 9/9 اختبارات وPiper فقط، بينما الكود 34 اختباراً وثلاثة محركات.
- القاعدة الذهبية: أي محرك جديد يُضاف خلف `UnifiedTTSEngine` ويُرجع نفس الكائنات، ولا يُلمس `main.py` إلا لزر اختيار.
