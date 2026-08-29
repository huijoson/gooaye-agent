"""Explicit catalog of the Topic Guides included in a publication."""

from domain import TopicDefinition


DEFAULT_TOPICS: tuple[TopicDefinition, ...] = (
    TopicDefinition(
        slug="ai-hardware-and-semiconductor",
        title="AI 伺服器、散熱、電力與 ASIC 自研晶片演進",
        description="追蹤 2021 至 2026 年主委對 AI 伺服器散熱（氣冷/水冷/CDU）、800V 高壓電力、CSP 自研 ASIC 晶片與 CoWoS 先進封裝之論述脈絡與產業轉折。",
        category="產業與硬體架構",
        keywords=(
            "ASIC", "自研晶片", "散熱", "水冷", "氣冷", "CDU", "GB200", "COT",
            "CoWoS", "TPU", "Trainium", "先進封裝", "伺服器", "800V", "高壓",
            "電源", "液冷", "快接頭", "電力", "機櫃",
        ),
        core_concepts=("水冷與散熱升級", "CSP 自研 ASIC 與客製化晶片", "CoWoS 與先進封裝瓶頸", "資料中心電力與 800V 架構"),
    ),
    TopicDefinition(
        slug="investment-mindset-and-risk-control",
        title="主委投資心態、部位管理、停損紀律與期望值實戰守則",
        description="彙整謝孟恭（主委）歷年關於交易心態、部位控制、停損停利紀律、勝率/賠率期望值計算與生活化哲學之精華觀念。",
        category="投資心態與風險控制",
        keywords=(
            "心態", "部位", "停損", "期望值", "賠率", "勝率", "追高", "拗單",
            "套牢", "槓桿", "紀律", "見仁見智", "CP值", "回吐", "雜音", "破線",
            "月線", "配置", "風險", "攤平",
        ),
        core_concepts=("睡得著覺的部位控管", "嚴格停損與拒絕拗單", "勝率賠率與正期望值下注", "過濾市場雜音與獨立思考"),
    ),
    TopicDefinition(
        slug="macro-cycle-and-asset-allocation",
        title="總體經濟循環、聯準會降息循環、房產與資產配置",
        description="整理主委對景氣循環位階、聯準會（Fed）利率政策、通膨與 CPI、美股與台股資產配置以及台灣房地產市場之觀點演進。",
        category="總體經濟與資產配置",
        keywords=(
            "總經", "降息", "升息", "聯準會", "Fed", "通膨", "CPI", "循環",
            "景氣", "房產", "房地產", "資產配置", "債券", "美債", "殖利率",
            "大盤", "指數", "衰退",
        ),
        core_concepts=("聯準會貨幣政策與利率循環", "股債與房產長線資產配置", "景氣週期位置判斷與應對"),
    ),
    TopicDefinition(
        slug="apple-and-consumer-electronics",
        title="Apple 供應鏈、智慧型手機與消費性電子週期",
        description="探討 Apple iPhone、Vision Pro、Mac/iPad 產品週期、台廠果鏈供應商消長、折疊機與消費性電子拉貨動能演變。",
        category="消費性電子與供應鏈",
        keywords=(
            "Apple", "蘋果", "iPhone", "Mac", "iPad", "Vision Pro", "果鏈",
            "供應鏈", "鏡頭", "聲學", "組裝", "消費性", "手機", "折疊",
            "PC", "NB", "庫存", "拉貨",
        ),
        core_concepts=("Apple 規格升級與供應鏈受惠", "消費性電子庫存去化與拉貨循環", "新硬體平台與應用驗證"),
    ),
)
