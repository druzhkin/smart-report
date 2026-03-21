from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


SHORT_OUTPUT_PATH = Path(r"C:\Users\rodina-adm\Documents\dev\smart-report\CustDev_PsyAssist_Интервью_рус.docx")
LONG_OUTPUT_PATH = Path(r"C:\Users\rodina-adm\Documents\dev\smart-report\CustDev_PsyAssist_Интервью_развернутый.docx")


ACCENT = "2F5D50"
TEXT = "333333"
MUTED = "666666"
BORDER = "D9D9D9"


CONTENT = [
    ("title", "CustDev-интервью для PsyAssist"),
    ("subtitle", "Короткая форма для разговора с психотерапевтом"),
    ("lead", "Цель интервью: понять, насколько продукт действительно нужен в практике, какие задачи он должен решать в первую очередь и какие доработки повысят ценность и доверие."),
    ("section", "Как использовать"),
    ("p", "Формат: 20-30 минут, спокойный полуструктурированный разговор."),
    ("p", "Логика: сначала понять, как человек работает сейчас, затем обсудить продукт, а в конце уточнить условия, при которых он был бы готов попробовать его в работе."),
    ("note", "Важно: не перегружать собеседника. Лучше задать 6-8 сильных вопросов и уточнить детали на реальных примерах, чем пройтись по длинному списку поверхностно."),
    ("section", "Короткое вступление"),
    ("quote", "Я делаю инструмент для психотерапевтов, который помогает с документацией, анализом сессий и подготовкой к дальнейшей работе с клиентом. Хочу лучше понять, как это устроено у вас сейчас, что действительно неудобно и что могло бы быть полезно в реальной практике."),
    ("section", "Основные вопросы"),
    ("q", "1. Как у вас сейчас устроена работа после сессии: заметки, ноты, фиксация важных наблюдений, подготовка к следующей встрече?"),
    ("q", "2. Что в этом процессе отнимает у вас больше всего времени или сил?"),
    ("q", "3. Бывает ли, что важные детали по клиенту теряются между сессиями или собираются слишком фрагментарно?"),
    ("q", "4. Если бы система помогала автоматически собирать ноты, концептуализацию и краткую аналитику по сессиям, что из этого было бы для вас действительно ценным, а что лишним?"),
    ("q", "5. Где вы бы точно не стали доверять AI без своей проверки?"),
    ("q", "6. Что должно быть в таком продукте, чтобы вы хотя бы попробовали использовать его в своей практике?"),
    ("q", "7. Чего в подобных решениях обычно не хватает именно с вашей профессиональной точки зрения?"),
    ("q", "8. Если инструмент реально экономил бы время и помогал держать целостную картину по клиенту, готовы ли вы были бы рассматривать платное использование? В каком формате это было бы для вас нормально?"),
    ("section", "Если времени мало"),
    ("p", "Можно ограничиться даже четырьмя вопросами:"),
    ("bullet", "Как вы сейчас ведёте пост-сессионную работу и что в ней неудобно?"),
    ("bullet", "Что из функций такого инструмента было бы для вас по-настоящему полезно?"),
    ("bullet", "Какие риски или сомнения мешали бы вам использовать это в практике?"),
    ("bullet", "При каких условиях вы были бы готовы попробовать такой продукт?"),
    ("section", "Что зафиксировать после разговора"),
    ("bullet", "Главная боль собеседника."),
    ("bullet", "Самый ценный сценарий использования."),
    ("bullet", "Главный барьер: доверие, безопасность, качество, этика, цена или другое."),
    ("bullet", "Какая доработка повысила бы вероятность внедрения сильнее всего."),
    ("closing", "Хорошее custdev-интервью не продаёт продукт. Оно помогает понять, где у специалиста уже есть реальная боль, а где пока только любопытство."),
]


LONG_CONTENT = [
    ("title", "CustDev-интервью для PsyAssist"),
    ("subtitle", "Развернутый сценарий интервью для глубинных разговоров с психотерапевтами"),
    ("lead", "Цель интервью: глубже понять рабочий процесс специалиста, реальную ценность продукта, барьеры доверия и приоритетные доработки, которые сделают инструмент полезным в реальной практике."),
    ("section", "Как использовать"),
    ("p", "Формат: 30-45 минут, спокойный разговор без давления и без попытки сразу продать решение."),
    ("p", "Основной принцип: сначала разбирать текущую практику и реальные трудности, потом обсуждать реакцию на продукт и только в конце переходить к вопросам внедрения и оплаты."),
    ("note", "Лучшие ответы появляются не на абстрактный вопрос «нужно ли это?», а на обсуждение конкретных случаев: как специалист работает сейчас, что теряет, чего опасается и что уже пытался использовать."),
    ("section", "Вступление"),
    ("quote", "Я работаю над инструментом для психотерапевтов, который помогает с документацией, анализом сессий и подготовкой к дальнейшей работе с клиентом. Мне важно понять не просто реакцию на идею, а то, как это могло бы встроиться в реальную практику: где это может быть полезно, а где будет мешать или вызывать недоверие."),
    ("section", "Блок 1. Контекст практики"),
    ("q", "1. Расскажите, пожалуйста, немного о вашей практике: с какими запросами и клиентами вы чаще всего работаете?"),
    ("q", "2. В каких подходах вы в основном работаете сейчас?"),
    ("q", "3. Насколько у вас сейчас плотная практика: сколько примерно сессий в неделю?"),
    ("q", "4. Вы работаете как частный специалист или внутри команды, центра, клиники?"),
    ("q", "5. Есть ли у вас обязательные требования к ведению документации, заметок или отчетности?"),
    ("section", "Блок 2. Как устроена работа сейчас"),
    ("q", "6. Что обычно происходит у вас сразу после завершения сессии?"),
    ("q", "7. Как вы сейчас фиксируете ноты, гипотезы, динамику, домашние задания и важные наблюдения по клиенту?"),
    ("q", "8. Где вы храните эту информацию и как потом возвращаетесь к ней перед следующей встречей?"),
    ("q", "9. Сколько времени обычно уходит на такую работу после сессии?"),
    ("q", "10. Что в этом процессе для вас наиболее неудобно, утомительно или нестабильно?"),
    ("section", "Блок 3. Боль и цена проблемы"),
    ("q", "11. Где именно вы чаще всего теряете время или внимание?"),
    ("q", "12. Бывает ли, что важные детали по клиенту теряются между сессиями или восстанавливаются потом уже не полностью?"),
    ("q", "13. Насколько сложно удерживать целостную картину по клиенту на длинной дистанции?"),
    ("q", "14. Какие последствия бывают, если пост-сессионная работа сделана не очень качественно или откладывается?"),
    ("q", "15. Какие задачи вы бы с удовольствием делегировали, если бы были уверены в качестве результата?"),
    ("section", "Блок 4. Текущие инструменты и альтернативы"),
    ("q", "16. Чем вы уже пользуетесь для заметок, организации практики, шкал, хранения материалов или анализа?"),
    ("q", "17. Пробовали ли вы какие-либо AI-инструменты для транскрипции, заметок или аналитики?"),
    ("q", "18. Что в них оказалось полезным, а что не подошло?"),
    ("q", "19. Почему существующие решения не закрывают задачу полностью?"),
    ("section", "Блок 5. Реакция на продукт PsyAssist"),
    ("p", "Краткое описание для разговора: система принимает запись сессии и помогает автоматически собрать клинические ноты, концептуализацию, аналитику, сводку по клиенту и подготовку к следующей встрече."),
    ("q", "20. Если смотреть на такой продукт в целом, что в нём кажется вам наиболее ценным?"),
    ("q", "21. Что, наоборот, выглядит лишним, спорным или неочевидным?"),
    ("q", "22. Если бы вы начали пользоваться только одной функцией, что это было бы?"),
    ("q", "23. Что вызывает у вас наибольшую осторожность или профессиональный скепсис?"),
    ("section", "Блок 6. Проверка ключевых функций"),
    ("q", "24. Ноты по итогам сессии: насколько это было бы вам полезно и что в таких нотах обязательно должно быть?"),
    ("q", "25. Концептуализация и диаграмма Бек: было бы вам полезно видеть черновик концептуализации, собранный из нескольких сессий?"),
    ("q", "26. Аналитика сессий: какие типы аналитики действительно помогали бы в работе, а какие скорее создавали бы шум?"),
    ("q", "27. Сводка по клиенту на одном экране: насколько это важно для вас в реальной практике?"),
    ("q", "28. Подсказки во время сессии: это выглядело бы как поддержка или как помеха?"),
    ("q", "29. AI-ассистент между сессиями: в каких рамках это для вас допустимо, а в каких нет?"),
    ("section", "Блок 7. Доверие, безопасность и профессиональные границы"),
    ("q", "30. Где вы точно не стали бы доверять AI без своей проверки?"),
    ("q", "31. Какие ошибки системы были бы для вас просто неприятными, а какие абсолютно недопустимыми?"),
    ("q", "32. Какие требования по безопасности и конфиденциальности для вас обязательны?"),
    ("q", "33. Есть ли здесь юридические, этические или репутационные риски, которые вы считаете особенно важными?"),
    ("q", "34. Что должно быть доказано или реализовано, чтобы вы могли этому инструменту доверять?"),
    ("section", "Блок 8. Условия внедрения и оплаты"),
    ("q", "35. При каких условиях вы были бы готовы попробовать такой инструмент в своей практике?"),
    ("q", "36. Что должно произойти в первые недели использования, чтобы вы решили остаться с продуктом?"),
    ("q", "37. Если продукт реально экономит время и помогает лучше держать картину по клиенту, насколько для вас в принципе допустима платная модель?"),
    ("q", "38. Какой формат оплаты для вас выглядел бы наиболее естественно: подписка, оплата за сессии, за минуты, за число клиентов?"),
    ("q", "39. От чего в большей степени зависела бы готовность платить: от экономии времени, от качества аналитики, от удобства ведения практики или от чего-то ещё?"),
    ("section", "Блок 9. Доработки и приоритеты"),
    ("q", "40. Если бы мы могли улучшить только три вещи, что стоило бы сделать в первую очередь?"),
    ("q", "41. Чего сейчас чаще всего не хватает продуктам такого типа, с вашей профессиональной точки зрения?"),
    ("q", "42. Какой минимальный набор функций уже сделал бы такой продукт полезным лично для вас?"),
    ("q", "43. Что превратило бы его из «интересной идеи» в инструмент, который вы бы реально встроили в работу?"),
    ("section", "Завершение"),
    ("q", "44. Кому из коллег такой продукт мог бы быть особенно интересен и почему?"),
    ("q", "45. Можно ли будет вернуться к вам с новой версией, прототипом или уточняющими вопросами?"),
    ("section", "Что важно зафиксировать после интервью"),
    ("bullet", "Кто был собеседник: специализация, формат практики, нагрузка."),
    ("bullet", "Главная боль, которую он описал."),
    ("bullet", "Самый ценный сценарий использования."),
    ("bullet", "Что вызвало максимальное недоверие или сопротивление."),
    ("bullet", "Какая доработка сильнее всего увеличила бы вероятность внедрения."),
    ("bullet", "Есть ли сигнал к оплате или готовности тестировать продукт."),
    ("closing", "Развернутое интервью полезно не для того, чтобы услышать как можно больше мнений, а для того, чтобы отделить устойчивую рабочую потребность от вежливого интереса к новой технологии."),
]


def run_xml(text: str, *, size: int = 24, bold: bool = False, italic: bool = False, color: str = TEXT, font: str = "Calibri") -> str:
    props = [f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>', f'<w:color w:val="{color}"/>', f'<w:sz w:val="{size}"/>', f'<w:szCs w:val="{size}"/>']
    if bold:
        props.append("<w:b/>")
        props.append("<w:bCs/>")
    if italic:
        props.append("<w:i/>")
        props.append("<w:iCs/>")
    return f'<w:r><w:rPr>{"".join(props)}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def paragraph_xml(
    runs: list[str],
    *,
    before: int = 0,
    after: int = 120,
    line: int | None = None,
    left: int = 0,
    border_top: bool = False,
    border_bottom: bool = False,
    shading: str | None = None,
    keep_next: bool = False,
) -> str:
    ppr = ["<w:pPr>"]
    if before or after or line:
        spacing = f'<w:spacing w:before="{before}" w:after="{after}"'
        if line:
            spacing += f' w:line="{line}" w:lineRule="auto"'
        spacing += "/>"
        ppr.append(spacing)
    if left:
        ppr.append(f'<w:ind w:left="{left}"/>')
    if keep_next:
        ppr.append("<w:keepNext/>")
    if border_top or border_bottom:
        ppr.append("<w:pBdr>")
        if border_top:
            ppr.append(f'<w:top w:val="single" w:sz="6" w:space="12" w:color="{BORDER}"/>')
        if border_bottom:
            ppr.append(f'<w:bottom w:val="single" w:sz="6" w:space="12" w:color="{BORDER}"/>')
        ppr.append("</w:pBdr>")
    if shading:
        ppr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shading}"/>')
    ppr.append("</w:pPr>")
    return f"<w:p>{''.join(ppr)}{''.join(runs)}</w:p>"


def build_body(content: list[tuple[str, str]]) -> str:
    paragraphs: list[str] = []
    for kind, text in content:
        if kind == "title":
            paragraphs.append(paragraph_xml([run_xml(text, size=34, bold=True, color=ACCENT, font="Cambria")], after=140, keep_next=True))
        elif kind == "subtitle":
            paragraphs.append(paragraph_xml([run_xml(text, size=22, italic=True, color=MUTED)], after=260, border_bottom=True))
        elif kind == "lead":
            paragraphs.append(paragraph_xml([run_xml(text, size=23)], after=220, line=360))
        elif kind == "section":
            paragraphs.append(paragraph_xml([run_xml(text, size=26, bold=True, color=ACCENT, font="Cambria")], before=180, after=120, keep_next=True))
        elif kind == "note":
            paragraphs.append(paragraph_xml([run_xml(text, size=21, italic=True, color=TEXT)], before=40, after=200, left=220, shading="F4F6F4"))
        elif kind == "quote":
            paragraphs.append(paragraph_xml([run_xml(text, size=22, italic=True, color=TEXT)], after=220, left=300, shading="F8F8F8"))
        elif kind == "q":
            paragraphs.append(paragraph_xml([run_xml(text, size=24, bold=False, color=TEXT)], before=40, after=120, line=340))
        elif kind == "bullet":
            paragraphs.append(paragraph_xml([run_xml(f"• {text}", size=22, color=TEXT)], before=0, after=80, left=260))
        elif kind == "closing":
            paragraphs.append(paragraph_xml([run_xml(text, size=21, italic=True, color=MUTED)], before=220, after=120, border_top=True))
        else:
            paragraphs.append(paragraph_xml([run_xml(text, size=22, color=TEXT)], after=120, line=340))
    return "".join(paragraphs)


def build_document_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{build_body(CONTENT)}<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1100" w:right="1150" w:bottom="1100" w:left="1150" w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr></w:body></w:document>"
    )


def build_long_document_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{build_body(LONG_CONTENT)}<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1100" w:right="1150" w:bottom="1100" w:left="1150" w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr></w:body></w:document>"
    )


CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""


RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>CustDev-интервью для PsyAssist</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dc:language>ru-RU</dc:language>
</cp:coreProperties>
"""


APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Office Word</Application>
</Properties>
"""


def write_docx(output_path: Path, document_xml: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        docx.writestr("_rels/.rels", RELS_XML)
        docx.writestr("docProps/core.xml", CORE_XML)
        docx.writestr("docProps/app.xml", APP_XML)
        docx.writestr("word/document.xml", document_xml)


def main() -> None:
    if not SHORT_OUTPUT_PATH.exists():
        write_docx(SHORT_OUTPUT_PATH, build_document_xml())
    write_docx(LONG_OUTPUT_PATH, build_long_document_xml())
    print(SHORT_OUTPUT_PATH)
    print(LONG_OUTPUT_PATH)


if __name__ == "__main__":
    main()
