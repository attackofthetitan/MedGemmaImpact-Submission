from models import RAGChunk


KNOWLEDGE_BASE = [
    RAGChunk(
        chunk_id="SOP001",
        source="chest_pain_protocol_v2.pdf",
        source_type="sop",
        content="""胸痛評估流程：
1. 立即評估ABC和生命徵象
2. 12導程心電圖在10分鐘內完成
3. PQRST問診：部位(Position)、性質(Quality)、放射(Radiation)、嚴重度(Severity)、時間(Timing)
4. 紅旗症狀：冒冷汗、呼吸困難、放射至左臂/下巴/背部、噁心嘔吐、暈厥
5. 風險分層：HEART score評估
6. 高風險者(HEART≥4)：立即轉診急診，考慮ACS pathway
7. 低風險者：門診追蹤，安排運動心電圖""",
        relevance_score=0.95,
    ),
    RAGChunk(
        chunk_id="SOP002",
        source="diabetes_management_v3.pdf",
        source_type="sop",
        content="""糖尿病照護流程：
1. HbA1c目標：一般<7%，老年人可放寬至<8%
2. 監測頻率：HbA1c每3個月，腎功能每年，眼底檢查每年
3. 藥物調整原則：
   - HbA1c 7-8%：優化口服藥
   - HbA1c 8-9%：考慮加第二線口服藥或GLP-1
   - HbA1c >9%：考慮起始胰島素
4. 併發症篩檢：尿液微白蛋白、足部檢查每次就診
5. 生活型態：飲食控制、規律運動、戒菸""",
        relevance_score=0.92,
    ),
    RAGChunk(
        chunk_id="SOP003",
        source="heart_failure_management.pdf",
        source_type="sop",
        content="""心衰竭管理指引：
1. 分類：HFrEF (EF<40%), HFmrEF (40-49%), HFpEF (≥50%)
2. 基礎治療(HFrEF)：ACEi/ARB/ARNI + Beta-blocker + MRA + SGLT2i
3. 利尿劑：依症狀和容積狀態調整
4. 監測：每日體重、症狀日記、定期BNP/NT-proBNP
5. 警示症狀需緊急評估：
   - 休息時呼吸困難
   - 端坐呼吸
   - 體重3天內增加>2kg
   - 下肢水腫惡化
6. 衛教重點：限鈉<2g/天、限水(嚴重者)、規律服藥、避免NSAIDs""",
        relevance_score=0.90,
    ),
    RAGChunk(
        chunk_id="SOP004",
        source="anticoagulation_protocol.pdf",
        source_type="sop",
        content="""抗凝血治療管理：
1. Warfarin監測：INR目標2.0-3.0(Afib)，每週至穩定後每月
2. 藥物交互作用注意：
   - 增強效果：抗生素、Amiodarone、NSAID
   - 減弱效果：Vitamin K食物、Rifampin
3. 出血風險評估：HAS-BLED score
4. 緊急處理：
   - 輕微出血：暫停1-2劑
   - 嚴重出血：Vitamin K、FFP、PCC
5. 手術前處理：依出血風險停藥3-5天""",
        relevance_score=0.88,
    ),
    RAGChunk(
        chunk_id="EDU001",
        source="patient_education_chest_pain.md",
        source_type="education",
        content="""何時應該叫救護車（119）：
- 胸口有壓迫感、緊縮感超過15分鐘
- 胸痛伴隨冒冷汗、噁心
- 呼吸困難、喘不過氣
- 疼痛放射到手臂、下巴、背部
- 感覺快要昏倒
- 心跳很快或不規則

這些可能是心臟病發作的徵兆，請立即撥打119，不要自己開車就醫。
在等待救護車時：
- 保持冷靜，坐下或躺下
- 鬆開緊身衣物
- 如果有舌下硝酸甘油，依醫囑使用""",
        relevance_score=0.93,
    ),
    RAGChunk(
        chunk_id="EDU002",
        source="patient_education_diabetes.md",
        source_type="education",
        content="""糖尿病自我照護須知：
1. 血糖監測：
   - 空腹血糖目標：80-130 mg/dL
   - 餐後2小時：<180 mg/dL
2. 低血糖警示（血糖<70）：
   - 症狀：冒冷汗、發抖、心悸、頭暈、飢餓感
   - 處理：立即吃15克糖（3顆方糖或半杯果汁）
   - 15分鐘後再測，必要時重複
3. 足部照護：
   - 每天檢查雙腳有無傷口、水泡
   - 不要赤腳走路
   - 穿合適的鞋子
4. 定期回診：
   - 每3個月：HbA1c、血壓
   - 每年：眼底檢查、腎功能、足部評估""",
        relevance_score=0.91,
    ),
    RAGChunk(
        chunk_id="EDU003",
        source="patient_education_heart_failure.md",
        source_type="education",
        content="""心衰竭自我照護須知：
1. 每日監測：
   - 每天早上量體重（空腹、排尿後）
   - 記錄呼吸狀況
2. 警示症狀（需立即就醫）：
   - 3天內體重增加超過2公斤
   - 躺下時呼吸困難，需要墊高枕頭
   - 腳腫惡化
   - 休息時也喘
   - 咳嗽加劇或咳粉紅色痰
3. 飲食控制：
   - 限鹽：每天少於2克（約半茶匙）
   - 避免醃製食品、罐頭、加工食品
   - 嚴重時可能需要限水
4. 藥物服用：
   - 按時服藥，不可自行停藥
   - 避免使用止痛藥（NSAIDs）""",
        relevance_score=0.89,
    ),
    RAGChunk(
        chunk_id="PROTO001",
        source="lab_critical_values.pdf",
        source_type="protocol",
        content="""危急值通報標準：
- 血糖：<50 或 >500 mg/dL
- 血鉀：<2.5 或 >6.5 mEq/L
- 血鈉：<120 或 >160 mEq/L
- INR：>5.0（正在使用Warfarin患者）
- Hemoglobin：<7.0 g/dL
- 血小板：<50,000 /uL
- Troponin：>正常上限（需臨床相關性判斷）
- Creatinine：急性上升>0.5 mg/dL

通報流程：實驗室→值班護理師→主治醫師（30分鐘內）""",
        relevance_score=0.87,
    ),
]


def search_knowledge(query: str, top_k: int = 3) -> list[RAGChunk]:
    """Keyword-based search over the knowledge base."""
    query_lower = query.lower()
    keywords_map = {
        "胸": ["SOP001", "EDU001"],
        "chest": ["SOP001", "EDU001"],
        "糖尿": ["SOP002", "EDU002"],
        "diabetes": ["SOP002", "EDU002"],
        "血糖": ["SOP002", "EDU002", "PROTO001"],
        "心衰": ["SOP003", "EDU003"],
        "heart failure": ["SOP003", "EDU003"],
        "喘": ["SOP003", "EDU003"],
        "呼吸": ["SOP001", "SOP003", "EDU001", "EDU003"],
        "抗凝": ["SOP004"],
        "warfarin": ["SOP004"],
        "inr": ["SOP004", "PROTO001"],
        "危急": ["PROTO001"],
        "critical": ["PROTO001"],
    }

    matched_ids = set()
    for keyword, chunk_ids in keywords_map.items():
        if keyword in query_lower:
            matched_ids.update(chunk_ids)

    if not matched_ids:
        matched_ids = {"SOP001", "SOP002", "EDU001"}

    chunks = [c for c in KNOWLEDGE_BASE if c.chunk_id in matched_ids]
    chunks.sort(key=lambda x: x.relevance_score, reverse=True)
    return chunks[:top_k]
