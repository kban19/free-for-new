"""Preliminary pages: Arabic cover, title page, approval, dedication, abstract, indexes."""
from __future__ import annotations

from docx.enum.section import WD_SECTION

import docx_bidi as D
import thesis_common as T

UNIVERSITY_AR = "جامعة روجآفا – قامشلو"
FACULTY_AR = "كلية العلوم الطبيعية والتكنولوجيا"
DEPARTMENT_AR = "قسم هندسة الحاسوب – فرع الشبكات"
AUTHORITY_AR = "الإدارة الذاتية الديمقراطية لإقليم شمال وشرق سوريا"
COUNCIL_AR = "مجلس جامعات إقليم شمال وشرق سوريا"

TITLE_AR = "تصميم وتطوير نظام ذكي لتحويل النص إلى كلام باللغتين الكرمانجية والعربية"

STUDENTS = (
    ("لقمان آلا حسين", "ZKB-042"),
    ("شرفان محمود عبده", "ZKB-035"),
    ("أمينة فريح حسين", "ZKB-010"),
)
SUPERVISOR = "المهندس أمين علي"
DEPARTMENT_HEAD = "المهندس كلش سليمان"
ACADEMIC_YEAR = "2026-2027"

LOGO_NOTE = "يُدرج هنا شعار جامعة روجآفا الرسمي"
LOGO_FILE = "Rojava_University_Logo_for_Thesis.jpg"


def _logo_placeholder(doc) -> None:
    """Embed the official Rojava University logo if present, else a clean box."""
    from pathlib import Path
    logo_path = Path(__file__).resolve().parent.parent / "docs" / "assets" / "thesis" / LOGO_FILE
    if logo_path.exists():
        D.add_image(doc, str(logo_path), width_twips=1650, alt="University of Rojava Logo", rtl=True)
        return
    p = D.para(doc, "", rtl=True, align="center", space_before=8, space_after=2)
    pPr = p._p.get_or_add_pPr()
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    pBdr = D.get_or_add(pPr, "pBdr", D.PPR_ORDER)
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement("w:" + side)
        for k, v in (("val", "dashed"), ("sz", "6"), ("space", "12"), ("color", "BFBFBF")):
            e.set(qn("w:" + k), v)
        pBdr.append(e)
    D.add_text(p, LOGO_NOTE, True, size=10, color="808080")
    D.para(doc, LOGO_FILE, rtl=False, align="center", size=9, color="808080",
           space_before=0, space_after=2)


def build_cover(doc, ctx) -> None:
    """Arabic front cover: authority, university, faculty, title, students, year."""
    T.center_line(doc, AUTHORITY_AR, size=12)
    T.center_line(doc, COUNCIL_AR, size=12)
    T.center_line(doc, UNIVERSITY_AR, size=16, bold=True, space=4)
    T.center_line(doc, FACULTY_AR, size=14, bold=True, space=4)
    T.center_line(doc, DEPARTMENT_AR, size=12)

    _logo_placeholder(doc)
    D.para(doc, TITLE_AR, rtl=True, align="center", size=22, bold=True, line=1.4, space_before=6, space_after=8)

    D.para(doc, "مشروع تخرج مقدم إلى قسم هندسة الحاسوب – فرع الشبكات، "
                "كلية العلوم الطبيعية والتكنولوجيا، جامعة روجآفا، "
                "استكمالاً لمتطلبات نيل درجة البكالوريوس في هندسة الحاسوب.",
           rtl=True, align="center", size=14, line=1.4, space_after=10)

    T.center_line(doc, "إعداد الطلبة:", size=14, bold=True)
    for name, sid in STUDENTS:
        T.center_line(doc, f"{name}   —   {sid}", size=14, space=2)
    T.center_line(doc, f"بإشراف: {SUPERVISOR}", size=14, bold=True)
    T.center_line(doc, f"العام الدراسي: {ACADEMIC_YEAR}", size=14, bold=True)


def build_title_page(doc, ctx) -> None:
    """Plain title page with the full official data."""
    T.new_page(doc)
    T.center_line(doc, UNIVERSITY_AR, size=16, bold=True, space=6)
    T.center_line(doc, FACULTY_AR, size=14, bold=True, space=6)
    T.center_line(doc, DEPARTMENT_AR, size=14, space=18)

    D.para(doc, TITLE_AR, rtl=True, align="center", size=22, bold=True, line=1.5)
    D.para(doc, "", rtl=True, space_after=10)
    T.center_line(doc, "مشروع تخرج لنيل درجة البكالوريوس في هندسة الحاسوب", size=14, space=14)

    T.center_line(doc, "إعداد:", size=14, bold=True, space=4)
    for name, sid in STUDENTS:
        T.center_line(doc, f"{name}   —   {sid}", size=14, space=2)

    D.para(doc, "", rtl=True, space_after=10)
    T.center_line(doc, f"المشرف الرئيسي: {SUPERVISOR}", size=14, space=4)
    T.center_line(doc, f"رئيس القسم: {DEPARTMENT_HEAD}", size=14, space=4)
    D.para(doc, "", rtl=True, space_after=8)
    T.center_line(doc, f"العام الدراسي: {ACADEMIC_YEAR}", size=14, bold=True)


def build_approval(doc, ctx) -> None:
    """Official supervisor approval page, verbatim statement from the guide."""
    T.new_page(doc)
    D.heading(doc, "صفحة موافقة المشرف", 1, rtl=True, align="center", space_after=18)

    T.body(doc, "إننا نؤكد على أن المشروع المحدد الذي يحمل العنوان:")
    D.para(doc, TITLE_AR, rtl=True, align="center", size=14, bold=True, line=1.5,
           space_before=6, space_after=10)

    T.body(doc, "والذي أعد من قبل الطالب/ة:")
    names = "     ".join(f"{i + 1}- {name}" for i, (name, _) in enumerate(STUDENTS))
    D.para(doc, names, rtl=True, align="start", size=14, line=1.5, space_after=10)

    T.body(doc, "هو نتيجة دراسة علمية أنجزت تحت إشراف:")
    D.para(doc, f"1- المشرف الرئيسي: {SUPERVISOR}     من قسم: هندسة الحاسوب",
           rtl=True, align="start", size=14, line=1.5, space_after=4)
    D.para(doc, "2- المشرف المشارك: .......................................     من قسم: ......................",
           rtl=True, align="start", size=14, line=1.5, space_after=16)

    T.body(doc, "وقد اطّلعنا على محتوى المشروع وأقرّ بأهميته العلمية والعملية، "
                "ونوصي بقبوله لمناقشته من قبل لجنة المناقشة الموقّرة.")

    D.para(doc, "", rtl=True, space_after=14)
    D.para(doc, "التوقيع:", rtl=True, align="start", size=14, bold=True, space_after=6)

    T.table(doc, ctx, "تواقيع المشرفين", [
        ["الصفة", "الاسم", "التوقيع", "التاريخ"],
        ["المشرف الرئيسي", SUPERVISOR, "", "20 /      / "],
        ["المشرف المشارك", "", "", "20 /      / "],
    ], widths=[2100, 2900, 1900, 1786], size=12)


def build_dedication(doc, ctx) -> None:
    """Short dedication page (optional per the guide)."""
    T.new_page(doc)
    D.heading(doc, "الإهداء", 1, rtl=True, align="center", space_after=24)
    for line in (
        "إلى اللغة الكرمانجية التي حُفظت في الصدور قبل الكتب،",
        "وإلى كل طالب يحمل حرفاً واحداً من حروف Hawar كأمانة،",
        "إلى عوائلنا التي لم تبخل علينا بالوقت والدعم،",
        "وإلى أساتذتنا الذين علّمونا أن السؤال نصف الجواب،",
        "نُهدي هذا الجهد المتواضع.",
    ):
        D.para(doc, line, rtl=True, align="center", size=14, line=1.8, space_after=2)


def build_acknowledgements(doc, ctx) -> None:
    """Acknowledgments page."""
    T.new_page(doc)
    D.heading(doc, "الشكر والتقدير", 1, rtl=True, align="center", space_after=18)

    T.body(doc, "الحمد لله الذي وفّقنا لإتمام هذا المشروع، ثم الشكر الجزيل لجامعة روجآفا "
                "وكلية العلوم الطبيعية والتكنولوجيا وقسم هندسة الحاسوب على تهيئة البيئة "
                "العلمية التي احتضنت هذا العمل.")
    T.body(doc, f"ونشكر مشرفنا {SUPERVISOR} على متابعته الدقيقة، وعلى ملاحظاته التي "
                "أعادت ترتيب أفكارنا أكثر من مرة، وعلى صبره حين كانت النتائج لا تشبه التوقعات. "
                "كما نشكر رئيس القسم " + DEPARTMENT_HEAD + " وأعضاء الهيئة التدريسية "
                "على ما قدّموه من توجيه خلال سنوات الدراسة.")
    T.body(doc, "ونشكر كل من قرأ هذا العمل أو جرّب التطبيق وأبدى ملاحظة، فكل ملاحظة "
                "صغيرة كانت سبباً في تحسين نسخة لاحقة. وأخيراً، الشكر لعوائلنا التي "
                "تحمّلت ساعات عملنا الطويلة ودعمتنا دون مقابل.")


def build_abstract_ar(doc, ctx, new_page: bool = True) -> None:
    """Arabic abstract, kept to a single page as the guide requires."""
    if new_page:
        T.new_page(doc)
    D.heading(doc, "الملخص", 1, rtl=True, align="center", space_after=14)

    T.body(doc, "يعالج هذا المشروع مشكلة غياب أداة محلية تعمل دون إنترنت لتحويل النص "
                "المكتوب بالكرمانجية إلى كلام مفهوم، ويجمعها مع معالجة عربية فصيحة في "
                "التطبيق نفسه.")

    T.body(doc, "تم بناء تطبيق سطح مكتب بلغة Python وإطار Flet بواجهة Material 3 "
                "تدعم ثلاث لغات واجهة (العربية باتجاه RTL، والكرمانجية، والإنجليزية)، "
                "ويعمل التطبيق على المعالج المركزي فقط دون بطاقة رسوميات أو اتصال بالشبكة "
                "بعد تجهيز أولي واحد. يعتمد النظام على محرك موحّد UnifiedTTSEngine "
                "يوجّه الطلب إلى أحد ثلاثة أنماط: piper_kmr (نموذج Piper VITS المدرَّب "
                "على Kurmanji، بتردد 22,050 Hz وتسعين متحدثاً)، وmms_kmr وmms_ara "
                "(نموذجا Meta MMS عبر sherpa-onnx بتردد 16,000 Hz).")

    T.body(doc, "تتوزّع مسؤوليات النظام على سبع وحدات مستقلة: الواجهة، والتهيئة، "
                "ومعالجة النص، والمحركات، والصوت، والترجمة، والتنزيل الأولي. ويمرّ الطلب "
                "في مسار واحد ثابت: تحقّق من النص، ثم تطبيع Unicode من نوع NFC لحماية "
                "حروف Hawar، ثم تجهيز نطقي خاص بكل محرك، ثم توليد غير متزامن خارج خيط "
                "الواجهة، ثم تحقّق إلزامي من سلامة ترويسة ملف WAV قبل عرض النتيجة.")

    T.body(doc, "أظهرت الاختبارات الآلية نجاح 34 اختباراً من 34، وتحقّق اختبار المحرك "
                "الحقيقي من إنتاج ملفات صوتية صحيحة في الأنماط الثلاثة، مع بقاء حروف "
                "Hawar كاملة في المخرجات. وبلغ عامل الزمن الحقيقي RTF نحو 0.06 في أطول "
                "نصوص Piper، أي أسرع من الزمن الحقيقي بأكثر من ستة عشر ضعفاً على معالج "
                "محمول، بينما بقي بين 0.27 و0.30 في نمطي MMS. ولم يُنفَّذ بعد التقييم "
                "السمعي البشري، وتُركّ مواضعه موسومة صراحةً في الفصل الرابع.")

    T.body(doc, "يوصي المشروع بتوسيع التقييم السمعي، وإضافة نماذج كرمانجية أحدث، "
                "وتحسين معالجة الأرقام والمصطلحات الدخيلة، مع إبقاء النواتج في نطاق "
                "الاستخدام البحثي غير التجاري احتراماً لترخيص نماذج Meta MMS.")

    D.para(doc, "الكلمات المفتاحية: تحويل النص إلى كلام، الكرمانجية، حروف Hawar، "
                "VITS، Piper، Meta MMS، sherpa-onnx، Flet، تطبيق أوفلاين.",
           rtl=True, align="justify", size=12, bold=True, line=1.4, space_before=8)


def build_toc_and_indexes(doc, ctx) -> None:
    """Table of contents, index of tables, index of figures and abbreviations."""
    T.new_page(doc)
    D.add_toc(
        doc,
        instr='TOC \\o "1-3" \\h \\z \\u',
        title="فهرس المحتويات",
        hint="اضغط Ctrl+A ثم F9 لتحديث الفهرس وأرقام الصفحات.",
        rtl=True,
    )

    T.new_page(doc)
    D.add_toc(
        doc,
        instr='TOC \\h \\z \\t "TableCaption,1"',
        title="فهرس الجداول",
        hint="اضغط Ctrl+A ثم F9 لتحديث فهرس الجداول.",
        rtl=True,
    )

    T.new_page(doc)
    D.add_toc(
        doc,
        instr='TOC \\h \\z \\t "FigureCaption,1"',
        title="فهرس الأشكال",
        hint="اضغط Ctrl+A ثم F9 لتحديث فهرس الأشكال.",
        rtl=True,
    )

    T.new_page(doc)
    D.heading(doc, "جدول الاختصارات والرموز", 1, rtl=True, align="center", space_after=14)
    T.table(doc, ctx, "الاختصارات والرموز المستخدمة في الأطروحة", [
        ["الاختصار", "التوسعة", "المعنى"],
        ["TTS", "Text-to-Speech", "تحويل النص المكتوب إلى كلام مسموع"],
        ["VITS", "Conditional VAE with Adversarial Learning", "بنية توليدية شاملة للنص إلى موجة صوتية"],
        ["MMS", "Massively Multilingual Speech", "مشروع Meta لتوسيع تقنيات الكلام لأكثر من ألف لغة"],
        ["ONNX", "Open Neural Network Exchange", "صيغة محمولة لتشغيل الشبكات العصبية"],
        ["RTF", "Real-Time Factor", "زمن التوليد مقسوماً على مدة الصوت"],
        ["NFC", "Normalization Form C", "صيغة التطبيع المركّبة من معيار Unicode"],
        ["WAV", "Waveform Audio File Format", "صيغة ملف صوتي غير مضغوط"],
        ["RTL", "Right-to-Left", "اتجاه الكتابة من اليمين إلى اليسار"],
        ["LTR", "Left-to-Right", "اتجاه الكتابة من اليسار إلى اليمين"],
        ["CPU", "Central Processing Unit", "المعالج المركزي"],
        ["G2P", "Grapheme-to-Phoneme", "تحويل الحروف المكتوبة إلى فونيمات منطوقة"],
        ["PCM", "Pulse-Code Modulation", "تمثيل رقمي للموجة الصوتية"],
        ["API", "Application Programming Interface", "واجهة برمجة التطبيقات"],
    ], widths=[1900, 3400, 3386], size=11)


def build_front_matter(doc, ctx) -> None:
    """Assemble the whole preliminary part and open the Roman-numbered section."""
    D.clear_footer(doc.sections[0])
    build_cover(doc, ctx)
    build_title_page(doc, ctx)
    build_approval(doc, ctx)
    build_dedication(doc, ctx)
    build_acknowledgements(doc, ctx)

    # Preliminary pages: Roman numerals start at the Arabic abstract.
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    D.set_margins(sec, rtl=True)
    D.set_section_direction(sec, rtl=True)
    D.set_page_numbering(sec, "upperRoman", 1)
    D.add_footer_page_number(sec, rtl=True)

    build_abstract_ar(doc, ctx, new_page=False)
    build_toc_and_indexes(doc, ctx)
