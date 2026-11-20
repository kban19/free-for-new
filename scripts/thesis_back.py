"""Final parts: APA references, appendices, English/Kurdish abstracts and covers."""
from __future__ import annotations

from docx.enum.section import WD_SECTION

import docx_bidi as D
import thesis_common as T

TITLE_EN = ("Design and Development of an AI-Based Text-to-Speech System "
            "for Kurmanji Kurdish and Arabic")
TITLE_KU = ("Sêwirandin û pêşxistina pergaleke zîrek ji bo veguherandina nivîsê "
            "bo axaftinê bi zimanên Kurmancî û Erebî")


def build_references(doc, ctx) -> None:
    T.new_page(doc)
    D.heading(doc, "المراجع والمصادر", 1, rtl=True, align="center", space_after=16)
    T.body_plain(doc, "اعتُمد نظام APA الإصدار السابع في توثيق المراجع، ورُتّبت "
                      "المراجع العربية أولاً ثم الأجنبية، وكلاهما ترتيب هجائي.")

    D.para(doc, "أولاً: المراجع العربية", rtl=True, align="start", size=14, bold=True,
           space_before=8, space_after=8)

    arabic = (
        "جامعة روجآفا. (2026). دليل كتابة مشروع التخرج. كلية العلوم الطبيعية "
        "والتكنولوجيا، جامعة روجآفا، قامشلو، سوريا.",
        "فريق Kurmanji-TTS. (2026). Kurmanji-TTS: تطبيق سطح مكتب لتحويل النص إلى كلام "
        "بالكرمانجية والعربية (الإصدار 1.0.0) [برمجية حاسوب]. "
        "https://github.com/kban19/free-for-new",
    )
    for ref in arabic:
        D.para(doc, ref, rtl=True, align="start", size=14, line=1.5, space_after=10,
               first_line_indent=None)

    D.para(doc, "ثانياً: المراجع الأجنبية", rtl=True, align="start", size=14, bold=True,
           space_before=12, space_after=8)

    english = (
        "atenax. (2024). kurmanci-tts-piper [Model]. Hugging Face. "
        "https://huggingface.co/atenax/kurmanci-tts-piper",

        "Flet. (2024). Flet documentation: Build Flutter apps in Python. "
        "https://flet.dev/docs/",

        "Hunt, A. J., & Black, A. W. (1996). Unit selection in a concatenative speech "
        "synthesis system using a large speech database. In Proceedings of the IEEE "
        "International Conference on Acoustics, Speech, and Signal Processing "
        "(pp. 373-376). IEEE.",

        "k2-fsa. (2024). sherpa-onnx: Speech recognition, text-to-speech and speaker "
        "identification with next-generation Kaldi [Computer software]. GitHub. "
        "https://github.com/k2-fsa/sherpa-onnx",

        "Kim, J., Kong, J., & Son, J. (2021). Conditional variational autoencoder with "
        "adversarial learning for end-to-end text-to-speech. In Proceedings of the 38th "
        "International Conference on Machine Learning (PMLR 139, pp. 5530-5540).",

        "Kong, J., Kim, J., & Bae, J. (2020). HiFi-GAN: Generative adversarial networks "
        "for efficient and high fidelity speech synthesis. In Advances in Neural "
        "Information Processing Systems (Vol. 33, pp. 17022-17033).",

        "Microsoft. (2024). ONNX Runtime [Computer software]. https://onnxruntime.ai/",

        "Pratap, V., Tjandra, A., Shi, B., Tomasello, P., Babu, A., Kundu, S., Elkahky, "
        "A., Ni, Z., Vyas, A., Fazel-Zarandi, M., Baevski, A., Adi, Y., Zhang, X., Hsu, "
        "W.-N., Conneau, A., & Auli, M. (2023). Scaling speech technology to 1,000+ "
        "languages. arXiv. https://arxiv.org/abs/2305.13516",

        "PyInstaller Development Team. (2024). PyInstaller manual. "
        "https://pyinstaller.org/en/stable/",

        "Rhasspy. (2023). Piper: A fast, local neural text-to-speech system "
        "(Version 2023.11.14-2) [Computer software]. GitHub. "
        "https://github.com/rhasspy/piper",

        "Taylor, P. (2009). Text-to-speech synthesis. Cambridge University Press.",

        "Unicode Consortium. (2024). Unicode Standard Annex #15: Unicode normalization "
        "forms. https://www.unicode.org/reports/tr15/",

        "Zen, H., Tokuda, K., & Black, A. W. (2009). Statistical parametric speech "
        "synthesis. Speech Communication, 51(11), 1039-1064. "
        "https://doi.org/10.1016/j.specom.2009.04.004",
    )
    for ref in english:
        D.para(doc, ref, rtl=False, align="start", size=12, line=1.3, space_after=8)


def build_appendices(doc, ctx) -> None:
    def open_appendix(letter: str) -> None:
        """Each appendix restarts its own table numbering (أ-1, ب-1, ...)."""
        ctx["chapter"] = letter
        ctx["table_no"] = 0
        ctx["fig_no"] = 0

    # ---------------------------------------------------------------- Appendix A
    open_appendix("أ")
    T.new_page(doc)
    D.heading(doc, "الملحق أ: دليل التثبيت والتشغيل", 1, rtl=True, align="start")
    T.h2(doc, "أ-1 المتطلبات المسبقة")
    T.bullets(doc, [
        "Python 3.10 أو أحدث (النسخة المستخدمة في التطوير 3.12 و3.13).",
        "اتصال بالإنترنت لمرة واحدة فقط أثناء تشغيل أداة التجهيز.",
        "مساحة قرص لا تقل عن 400 ميغابايت للنماذج الثلاثة ومحرك Piper.",
        "Windows 10/11 للتشغيل الكامل، أو Linux مع حزمة aplay.",
    ])
    T.h2(doc, "أ-2 خطوات التثبيت")
    T.numbered(doc, [
        "إنشاء بيئة افتراضية: python -m venv .venv",
        "تفعيل البيئة: .venv\\Scripts\\activate على Windows أو source .venv/bin/activate على Linux.",
        "تثبيت الاعتماديات: pip install -r requirements.txt",
        "تنزيل المحرك والنماذج: python setup_runtime.py",
        "تشغيل التطبيق: python main.py",
    ])
    T.h2(doc, "أ-3 بناء النسخة التنفيذية")
    T.body(doc, "على Windows يُشغَّل السكربت scripts\\build_windows.bat فينتج "
                "dist\\Kurmanji-TTS.exe مع نسخ مجلدي models وpiper بجانبه. ويُفضّل "
                "استخدام بيئة .build-venv لأن حزمة sherpa-onnx لا تُثبَّت في بعض بيئات "
                "MSYS2. وعلى Linux يُشغَّل scripts/build_linux.sh بعد منحه صلاحية "
                "التنفيذ.")
    T.h2(doc, "أ-4 التحقق من نجاح التثبيت")
    T.body(doc, "أسرع تحقق هو تشغيل حزمة الاختبارات: "
                "python tests\\test_kurmanji_tts.py، ويُتوقع أن تنتهي بعبارة OK مع "
                "34 اختباراً. ثم تشغيل التطبيق والتأكد من ظهور شارة «النموذج جاهز» "
                "باللون الأخضر في الشريط العلوي.")

    # ---------------------------------------------------------------- Appendix B
    open_appendix("ب")
    T.new_page(doc)
    D.heading(doc, "الملحق ب: سجل القرارات الهندسية", 1, rtl=True, align="start")
    T.body(doc, "يوثّق هذا الملحق القرارات التي غيّرت مسار المشروع، والبديل الذي رُفض، "
                "والسبب الذي رجّح القرار المنفَّذ. والغرض منه أن يعرف القارئ لماذا "
                "يبدو الكود كما يبدو، لا كيف يعمل فقط.")
    T.table(doc, ctx, "القرارات الهندسية وأسبابها", [
        ["القرار", "البديل المرفوض", "سبب الترجيح"],
        ["Flet بدل Gradio", "خادم محلي في المتصفح", "تطبيق سطح مكتب حقيقي وتغليف واحد"],
        ["ثلاثة محركات خلف عقد واحد", "كود منفصل لكل محرك", "إضافة MMS دون لمس الواجهة"],
        ["إبقاء عملية Piper دافئة", "استدعاء منفرد لكل طلب", "توفير زمن تحميل النموذج"],
        ["تطبيع NFC", "لا تطبيع", "حفظ حروف Hawar ومنع الانقلاب الترميزي"],
        ["تحقق WAV إلزامي", "الثقة في مخرج المحرك", "منع عرض ملفات تالفة أو صامتة"],
        ["أسماء ملفات عشوائية", "اسم من نص المستخدم", "منع تسريب النص في أسماء الملفات"],
        ["تشغيل داخلي عبر winmm/aplay", "مشغل النظام الخارجي", "تجربة موحّدة بلا نوافذ"],
        ["فصل اتجاه الصفحة عن الحقل", "rtl واحد للكل", "كرمانجية لاتينية داخل واجهة عربية"],
        ["static captions + TOC fields", "SEQ fields لكل تسمية", "طباعة بلا حقول غير محدّثة"],
    ], widths=[3000, 2600, 3086], size=9)

    # ---------------------------------------------------------------- Appendix C
    open_appendix("ج")
    T.new_page(doc)
    D.heading(doc, "الملحق ج: حالات الاختبار", 1, rtl=True, align="start")
    T.body(doc, "يُعرض هنا نموذج من حالات الاختبار المهمة مع المدخل المتوقع والمخرج "
                "الفعلي. والحزمة الكاملة (34 اختباراً) موجودة في "
                "tests/test_kurmanji_tts.py.")
    T.table(doc, ctx, "حالات اختبار مختارة", [
        ["الحالة", "المدخل", "المتوقع", "النتيجة"],
        ["تطبيع NFC", "نص بحرف Ç بصيغة NFD", "نص NFC وكل حروف Hawar موجودة", "نجح"],
        ["نص فارغ", "مسافات وأسطر فقط", "رفض مع رسالة", "نجح"],
        ["نص رموز", "!!! ???", "رفض لأنه لا كلمات", "نجح"],
        ["نص طويل", "5001 حرف", "رفض مع ذكر الحد", "نجح"],
        ["سرعة 0.5", "length_scale = 2.0", "مدة أطول بأكثر من الضعف", "نجح"],
        ["متحدث 999", "معرّف خارج النطاق", "استثناء TTSEngineError", "نجح"],
        ["قاموس النطق", "PDF û USB", "pî dî ef û yû es bî", "نجح"],
        ["عربي مع تشكيل", "الطالبُ قرأَ 2026", "بقاء الضمة و2026", "نجح"],
        ["تصفية MMS", "نص فيه أقواس وتعجب", "حذف الرموز غير المعروفة", "نجح"],
        ["ترجمة ناقصة", "مفتاح مفقود في لغة", "فشل الاختبار", "نجح"],
        ["مشغل خارجي", "os.startfile في الكود", "فشل الاختبار", "نجح"],
        ["حفظ WAV", "مسار بلا امتداد", "إضافة .wav تلقائياً", "نجح"],
    ], widths=[2200, 2700, 2686, 1100], size=9)

    # ---------------------------------------------------------------- Appendix D
    open_appendix("د")
    T.new_page(doc)
    D.heading(doc, "الملحق د: استبيان التقييم السمعي", 1, rtl=True, align="start")
    T.body(doc, "الغرض: قياس جودة النطق في الأنماط الثلاثة بمقياس من خمس درجات. "
                "لم تُنفَّذ الجلسات بعد، وهذا الملحق هو الأداة الجاهزة لتنفيذها.")
    T.h2(doc, "د-1 بيانات المشارك")
    T.table(doc, ctx, "بيانات المشارك", [
        ["الحقل", "القيمة"],
        ["الرمز التعريفي", ""],
        ["هل اللغة الأم كرمانجية؟", "نعم / لا"],
        ["هل تجيد العربية الفصحى؟", "نعم / لا"],
        ["نوع السماعات المستخدمة", ""],
    ], widths=[4200, 4486], size=10)
    T.h2(doc, "د-2 سلّم التقييم")
    T.table(doc, ctx, "سلّم التقييم الخماسي", [
        ["الدرجة", "المعنى"],
        ["5", "طبيعي تماماً، لا فرق عن كلام بشري"],
        ["4", "طبيعي مع عيوب بسيطة"],
        ["3", "مفهوم لكنه مسموع كصوت آلي"],
        ["2", "مفهوم بصعوبة"],
        ["1", "غير مفهوم أو غير مسموع"],
    ], widths=[2000, 6686], size=10)
    T.body(doc, "تُعرض على المشارك ست عيّنات لكل نمط، ويُطلب منه تقييم كل عيّنة على "
                "أربعة أبعاد: الوضوح، والطبيعية، وصحة نطق حروف Hawar، والإيقاع. ثم "
                "يُحسب المتوسط والانحراف المعياري لكل بعد، وتُدوَّن النتائج في جدول "
                "(4-5) في الفصل الرابع.")

    # ---------------------------------------------------------------- Appendix E
    open_appendix("هـ")
    T.new_page(doc)
    D.heading(doc, "الملحق هـ: استكشاف الأخطاء وإصلاحها", 1, rtl=True, align="start")
    T.table(doc, ctx, "الأعراض والأسباب والحلول", [
        ["العرض", "السبب المحتمل", "الحل"],
        ["«محرك Piper غير موجود»", "لم يُشغَّل setup_runtime أو المسار خاطئ", "شغّل setup_runtime أو حدّد المسار من الإعدادات"],
        ["«ملفات النموذج غير مكتملة»", "ملف onnx أو json مفقود", "أعد التجهيز وتأكد من وجود الملفين"],
        ["«sherpa-onnx غير مثبت»", "الحزمة غير موجودة في البيئة", "ثبّتها في بيئة البناء .build-venv"],
        ["صوت صامت", "تردد أو جهاز إخراج", "تحقق من get_length_ms واختبار نغمة"],
        ["لا يعمل aplay", "حزمة الصوتيات غير مثبتة", "ثبّت حزم ALSA على Linux"],
        ["نسخة exe لا تجد النماذج", "النماذج ليست بجانب الملف التنفيذي", "انسخ مجلد models بجانب exe"],
        ["فشل التثبيت على MSYS2", "wheel غير متوافق", "استخدم .build-venv"],
    ], widths=[2500, 2800, 3386], size=9)


def build_abstract_en(doc, ctx) -> None:
    T.new_page(doc)
    D.heading(doc, "Abstract", 1, rtl=False, align="center", space_after=14)
    for text in (
        "This project addresses the absence of a fully offline tool that converts "
        "Kurmanji Kurdish text, written in the Hawar Latin alphabet, into intelligible "
        "speech while also supporting Modern Standard Arabic within the same "
        "application.",

        "The delivered system is a desktop application written in Python with the Flet "
        "framework and a Material 3 interface supporting three interface languages "
        "(Arabic with right-to-left layout, Kurmanji and English). It runs entirely on "
        "the CPU, requires no graphics card, and needs no network connection after a "
        "single setup step. A unified engine, UnifiedTTSEngine, routes each request to "
        "one of three profiles: piper_kmr (a Piper VITS model at 22,050 Hz with ninety "
        "speakers), mms_kmr and mms_ara (Meta MMS voices served through sherpa-onnx at "
        "16,000 Hz).",

        "The system is divided into seven single-responsibility modules: interface, "
        "configuration, text processing, engines, audio, localisation and runtime "
        "setup. Every request follows one fixed pipeline: validate the text, normalise "
        "it to Unicode NFC to protect Hawar characters, prepare engine-specific "
        "pronunciation input, synthesise off the UI thread, then validate the WAV "
        "header and frame count before the result is shown.",

        "The automated suite passes 34 of 34 tests. A real-engine smoke test produced "
        "valid, non-silent audio for all three profiles with no missing Hawar letters. "
        "The real-time factor reached approximately 0.06 for the longest Piper input, "
        "more than sixteen times faster than real time on a laptop CPU, while the MMS "
        "profiles stayed between 0.27 and 0.30. A human listening test using the MOS "
        "scale has not yet been conducted, and its cells are explicitly marked as "
        "pending in Chapter Four.",

        "The project recommends completing a formal listening evaluation, adding newer "
        "Kurmanji models, and improving number and loanword handling, while keeping "
        "outputs within non-commercial research use in accordance with the CC-BY-NC 4.0 "
        "licence of the Meta MMS models.",
    ):
        D.para(doc, text, rtl=False, align="justify", size=14, line=1.5, space_after=8)

    D.para(doc, "Keywords: text-to-speech, Kurmanji, Hawar alphabet, VITS, Piper, "
                "Meta MMS, sherpa-onnx, Flet, offline desktop application.",
           rtl=False, align="start", size=12, bold=True, line=1.4, space_before=8)


def build_abstract_ku(doc, ctx) -> None:
    T.new_page(doc)
    D.heading(doc, "Kurte", 1, rtl=False, align="center", space_after=14)
    for text in (
        "Ev proje sepaneke serşokê (desktop) e ku nivîsa Kurmancî ya bi alfabeya Hawar "
        "û nivîsa Erebî ya standard vediguherîne axaftinê. Sepan bi temamî li ser CPU-ê "
        "dixebite, pêdivî bi karteke grafîkê tune, û piştî amadekirineke yekcar bê "
        "înternet jî bi tevahî dixebite.",

        "Sepan bi Python û çarçoveya Flet-ê hatiye çêkirin, bi navrûyeke Material 3 ku "
        "sê zimanên navrûyê piştgirî dike: Erebî (ji rastê bo çepê), Kurmancî û Îngilîzî. "
        "Motora yekgirtî UnifiedTTSEngine her daxwazê ber bi yek ji sê profîlan ve dişîne: "
        "piper_kmr (modela Piper VITS, 22,050 Hz, notûn axêver), mms_kmr û mms_ara "
        "(modelên Meta MMS bi sherpa-onnx, 16,000 Hz).",

        "Pergal li heft yekîneyên serbixwe hatiye dabeşkirin: navrû, mîheng, hilberîna "
        "nivîsê, motor, deng, werger û amadekirina pêşîn. Her daxwaz di rêyeke yek "
        "derbas dibe: kontrola nivîsê, normalîzekirina Unicode NFC ji bo parastina tîpên "
        "Hawar, amadekirina bilêvkirinê li gorî motorê, hilberîna deng li derveyî "
        "xêza navrûyê, û paşê kontrola mecbûrî ya pela WAV berî nîşandana encamê.",

        "Ceribandinên otomatîk 34 ji 34 derbas kirin, û ceribandina motora rastîn dengê "
        "durist ji bo her sê profîlan hilberand, bê ku tîpeke Hawar winda bibe. "
        "Faktora dema rastîn (RTF) li nêzîkê 0.06 bû ji bo dirêjtirîn nivîsa Piper, yanî "
        "ji dema rastîn zêdetirî şazdeh caran zûtir li ser CPU-ya laptopekê. Nirxandina "
        "guhdarîkirinê ya mirovan (MOS) hê nehatiye kirin û cihên wê di Beşa Çarem de "
        "bi awayekî eşkere vala hatine hiştin.",

        "Proje pêşniyar dike ku nirxandina guhdarîkirinê were temamkirin, modelên "
        "Kurmancî yên nûtir werin zêdekirin, û hilberîna hejmaran baştir bibe, bi "
        "şertê ku encam ji bo lêkolînê û ne ji bo bazirganiyê werin bikaranîn, li gorî "
        "lîsansa CC-BY-NC 4.0 ya modelên Meta MMS.",
    ):
        D.para(doc, text, rtl=False, align="justify", size=13, line=1.4, space_after=8)

    D.para(doc, "Peyvên sereke: veguherandina nivîsê bo axaftinê, Kurmancî, alfabeya "
                "Hawar, VITS, Piper, Meta MMS, sherpa-onnx, Flet.",
           rtl=False, align="start", size=12, bold=True, line=1.4, space_before=8)


def build_final_covers(doc, ctx) -> None:
    """English cover and Kurdish back cover, LTR, no page numbers."""
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    D.set_margins(sec, rtl=False)
    D.set_section_direction(sec, rtl=False)
    # new sections inherit the previous pgNumType; the covers must not restart at 1
    D.drop(sec._sectPr, "pgNumType")
    D.clear_footer(sec)

    D.para(doc, "University of Rojava - Qamishli", rtl=False, align="center",
           size=14, bold=True, space_after=2)
    D.para(doc, "Faculty of Natural Sciences and Technology", rtl=False,
           align="center", size=13, bold=True, space_after=2)
    D.para(doc, "Department of Computer Engineering - Networks Branch", rtl=False,
           align="center", size=12, space_after=16)

    D.para(doc, "[Official university logo: Rojava_University_Logo_for_Thesis.jpg]",
           rtl=False, align="center", size=10, color="808080", space_after=16)

    D.para(doc, TITLE_EN, rtl=False, align="center", size=22, bold=True, line=1.5)
    D.para(doc, "", rtl=False, space_after=8)
    D.para(doc, "A graduation project submitted to the Department of Computer "
                "Engineering in partial fulfilment of the requirements for the degree "
                "of Bachelor of Science in Computer Engineering.",
           rtl=False, align="center", size=13, line=1.5, space_after=14)

    D.para(doc, "Prepared by:", rtl=False, align="center", size=13, bold=True, space_after=2)
    for name, sid in (("Luqman Ala Hussein", "ZKB-042"),
                      ("Shirvan Mahmoud Abdo", "ZKB-035"),
                      ("Amina Fareeh Hussein", "ZKB-010")):
        D.para(doc, f"{name}  -  {sid}", rtl=False, align="center", size=13,
               space_after=2)

    D.para(doc, "", rtl=False, space_after=6)
    D.para(doc, "Supervised by: Eng. Amin Ali", rtl=False, align="center",
           size=13, bold=True, space_after=2)
    D.para(doc, "Academic year: 2026-2027", rtl=False, align="center", size=13,
           bold=True, space_after=0)

    # -------------------------------------------------------------- Kurdish cover
    D.paragraph_with_page_break(doc, rtl=False)
    D.para(doc, "ZANÎNGEHA ROJAVA - QAMIŞLO", rtl=False, align="center",
           size=15, bold=True, space_after=2)
    D.para(doc, "F.Z. Xwezayî û Teknolojî", rtl=False, align="center",
           size=13, bold=True, space_after=2)
    D.para(doc, "Beşê Endezyariya Komputerê - Şaxa Torên", rtl=False, align="center",
           size=12, space_after=16)

    D.para(doc, "[Logoya zanîngehê: Rojava_University_Logo_for_Thesis.jpg]",
           rtl=False, align="center", size=10, color="808080", space_after=16)

    D.para(doc, TITLE_KU, rtl=False, align="center", size=22, bold=True, line=1.5)
    D.para(doc, "", rtl=False, space_after=10)
    D.para(doc, "Projeya mezûnbûnê ji bo Beşê Endezyariya Komputerê, "
                "F.Z. Xwezayî û Teknolojî, Zanîngeha Rojava.",
           rtl=False, align="center", size=13, line=1.5, space_after=14)

    D.para(doc, "Amadekar:", rtl=False, align="center", size=13, bold=True, space_after=2)
    for name in ("Luqman Ala Hussein", "Shirvan Mahmoud Abdo", "Amina Fareeh Hussein"):
        D.para(doc, name, rtl=False, align="center", size=13, space_after=2)
    D.para(doc, "", rtl=False, space_after=6)
    D.para(doc, "Şêwirmend: Eng. Amin Ali", rtl=False, align="center", size=13,
           bold=True, space_after=2)
    D.para(doc, "Sala xwendinê: 2026-2027", rtl=False, align="center", size=13,
           bold=True, space_after=0)
