# Stage2_4_After_LLM 工作流说明

## 一、整体数据流向

```
LLM抽取结果 (JSON数组)
        │
        ▼
  load_extracted_blocks()          ← 解析 JSONL 为 List[List[dict]]
        │
        ▼
  init_session(session_id, dov)    ← 创建空 MedicalRecordState
        │
        ▼
  route_and_transform(tags, dov)   ← 路由映射：标签 → 补丁字典
        │
        ▼
  _apply_patch(state, patch)       ← 状态合并：补丁写入状态机
        │
        ▼
  to_output_dict() → JSON文件      ← 输出结构化结果
```

### 1. 输入层：加载 LLM 抽取结果

- **入口**：`stage2_4_after_llm.py` → `load_extracted_blocks()`
- **来源文件**：`standard_llm_20.jsonl`（由上游 LLM 抽取阶段产出）
- **解析方式**：`_iter_json_arrays()` 逐字符解析，提取所有顶层 JSON 数组
- **数据格式**：每个数组代表一个 session，数组内每个元素为 `{key, value, term, raw}` 标签字典

### 2. 会话初始化

- **方法**：`PostStructureStage24.init_session()`
- **产出**：空的 `MedicalRecordState` 对象，包含以下 9 大子模块：

| 模块名 | Schema 类 | 说明 |
|--------|-----------|------|
| `obh` | `List[OBHEntry]` | 孕产史（核心孕产指标） |
| `hpi` | `HPI` | 现病史 |
| `pmh` | `PMH` | 既往史 |
| `additional_medical_history` | `AdditionalHistory` | 月经及婚育史 |
| `personal_history` | `PersonalHistory` | 个人史 |
| `fh` | `FamilyHistory` | 家族史 |
| `physicalExamination` | `PhysicalExam` | 全身体格检查 |
| `gynecologicalExamination` | `GynecologicalExam` | 产科/妇科专科检查 |
| `advice` | `Advice` | 医嘱/预约 |

### 3. 路由映射层（核心）：`route_and_transform()`

> 文件：`mapping.py:596-949`

这是整个流程最关键的环节，将 LLM 抽取的扁平标签字典转换为结构化的 `patch_data`。

**映射优先级**：

| 优先级 | 规则模块 | 说明 | 示例 |
|--------|----------|------|------|
| 1 | OBH 事件级写入 | 孕产史事件独立成条 | "剖宫产1次" → OBHEntry(cesareanSection=1) |
| 2 | 过敏特殊规则 | 区分药物/食物/其他过敏 | "青霉素过敏" → pmh.allergyDrug |
| 3 | 糖尿病/GDM 规则 | 区分妊娠期/既往糖尿病 | "GDM" → pmh.diabetes |
| 4 | 贫血/甲状腺规则 | 孕期写 hpi，既往写 pmh | "甲减" → hpi.otherNote 或 pmh.thyroidDisease |
| 5 | 胎心/胎儿字段 | 按胎儿索引写入 | "胎心140" → fetusExam[1].fetalHeartRate |
| 6 | **SCHEMA_MAP 精确映射** | key → domain.specificField | "高血压" → pmh.hypertension |
| 7 | **CATEGORIES_MAPPING 兜底路由** | 模糊匹配 → domain.otherNote | "蚕豆病" → pmh.otherNote |

**后处理步骤**：

1. OBH entries 合并输出
2. 孕周规范化（`_normalize_gwov`：如 "37周+4天" → "37+4"）
3. 孕周推算预产期（`infer_edd_from_gw`：孕周 + 就诊日期 → EDD）
4. 主诉兜底（无主诉时填入 "无不适，常规产检"）
5. 脉搏/心率互补
6. 术语规范化（`_normalize_patch_notes`：口语 → 医学术语）

### 4. 状态合并层：`_apply_patch()`

> 文件：`stage2_4_after_llm.py:27-172`

将 `patch_data` 中的值合并到 `MedicalRecordState`，核心合并策略：

| 字段类型 | 合并策略 | 说明 |
|----------|----------|------|
| `StatusDetail` | 状态优先级合并 | status=1 优先；同 status 时 details 用 `；` 拼接 |
| `*Note` 文本字段 | 追加去重 | 用 `；` 拼接，已有内容不重复 |
| `list` 字段 | extend 追加 | OBH children 特殊处理 |
| 普通字段 | 直接覆盖 | 新值替换旧值 |
| OBH 校验 | 反推孕次/产次 | 从 obh entries 推算 gravidity/parity，交叉校验 |

### 5. 输出层

- **方法**：`MedicalRecordState.to_output_dict()`
- **产出**：每个 session 一个 JSON 文件
- **特殊处理**：`fetusExam` 字典转为列表，嵌入 `gynecologicalExamination.fetusExam`

---

## 二、三层映射体系：SCHEMA_MAP / KEY_SYNONYMS / CATEGORIES_MAPPING

### 整体架构

```
LLM 输出的 key
      │
      ▼
┌──────────────────────────────────────┐
│  第1层：SCHEMA_MAP + KEY_SYNONYMS     │  精确映射 → domain.specificField
│  合并为 SCHEMA_MAP_EXPANDED           │
└──────────────┬───────────────────────┘
               │ 未命中
               ▼
┌──────────────────────────────────────┐
│  第2层：CATEGORIES_MAPPING            │  模糊匹配 → domain.otherNote
│  + CATEGORY_TO_NODE                   │
└──────────────┬───────────────────────┘
               │ 仍未命中
               ▼
         默认 → ('hpi', 'otherNote')
```

### 第1层：`SCHEMA_MAP` + `KEY_SYNONYMS` → `SCHEMA_MAP_EXPANDED`

**职责**：精确映射，将 key 直接路由到具体的 `domain.field`。

| 组件 | 定义位置 | 性质 | 示例 |
|------|----------|------|------|
| `SCHEMA_MAP` | `mapping.py:19-128` | 主映射表：key → `domain.field` | `"高血压" → "pmh.hypertension"` |
| `KEY_SYNONYMS` | `mapping_dicts.py:4-92` | 别名扩展：`domain.field` → 同义词列表 | `"pmh.hypertension" → ["高血压史","高血压病史"]` |

**合并过程**（`mapping.py:131-139`）：

```python
def _expand_schema_map(schema_map: dict) -> dict:
    expanded = dict(schema_map)
    for path, aliases in KEY_SYNONYMS.items():
        for alias in aliases:
            expanded[alias] = path        # 反转：别名 → schema path
    return expanded

SCHEMA_MAP_EXPANDED = _expand_schema_map(SCHEMA_MAP)
```

合并后 `SCHEMA_MAP_EXPANDED` 为扁平字典，一次 `dict.get(key)` 即可查找。

**查找代码**（`mapping.py:800`）：

```python
path = SCHEMA_MAP_EXPANDED.get(key)
```

### 第2层：`CATEGORIES_MAPPING` + `CATEGORY_TO_NODE`

**职责**：模糊兜底，当 key 不在第1层时，用关键词包含匹配判定所属分类。

| 组件 | 定义位置 | 性质 | 示例 |
|------|----------|------|------|
| `CATEGORIES_MAPPING` | `diagnosis_dic.py:1-23` | 分类关键词词典：category → keyword 列表 | `'3. 既往史 (PMH)' → ['地贫','贫血','癫痫',...]` |
| `CATEGORY_TO_NODE` | `mapping.py:142-151` | 分类→写入目标：category → `(domain, field)` | `'3. 既往史 (PMH)' → ('pmh', 'otherNote')` |

**查找代码**（`mapping.py:154-159`）：

```python
def find_domain_by_dict(key: str) -> tuple:
    for category, keywords in CATEGORIES_MAPPING.items():
        for kw in keywords:
            if kw in key:                                    # 包含匹配
                return CATEGORY_TO_NODE.get(category, ('hpi', 'otherNote'))
    return ('hpi', 'otherNote')                              # 最终兜底
```

### 第1层与第2层的关键区别

| 维度 | 第1层 (SCHEMA_MAP_EXPANDED) | 第2层 (CATEGORIES_MAPPING) |
|------|-----|-----|
| **匹配方式** | 精确等于 (`dict.get(key)`) | 关键词包含 (`kw in key`) |
| **映射粒度** | 精确到 `domain.specificField` | 只到 `domain.otherNote` |
| **值处理** | 按字段类型转换（int/float/date/StatusDetail） | 统一拼为 `"key: value"` 字符串 |
| **信息保留度** | 高（结构化写入） | 低（文本备注） |
| **维护成本** | 高（需逐条定义映射） | 低（只需补充分类关键词） |

### 举例对比

以 `key="高血压"` 为例：

| 层级 | 匹配结果 | 写入目标 | 值格式 |
|------|----------|----------|--------|
| 第1层 | `SCHEMA_MAP_EXPANDED["高血压"] = "pmh.hypertension"` | `pmh.hypertension` | `StatusDetail(status=1, details="患者高血压")` |
| 第2层（假设第1层未命中） | `CATEGORIES_MAPPING` 中 "高血压" ∈ 既往史 | `pmh.otherNote` | `"高血压: xxx"` |

**同一个 key，第1层产出结构化数据，第2层只能落为文本备注。**

### CATEGORIES_MAPPING 的完善意义

当 `CATEGORIES_MAPPING` 中缺少某个关键词时，该 key 将无法被正确分类，默认落入 `('hpi', 'otherNote')`，导致：
- 既往史信息被错误归类到现病史
- 个人史/家族史信息丢失分类
- 结构化数据降级为无结构文本

因此，持续补充 `CATEGORIES_MAPPING` 中的关键词，可以增强兜底路由的分类覆盖率，确保未精确映射的信息至少被正确归类到所属 domain。

---

## 三、文件依赖关系

```
stage2_4_after_llm.py          ← 主入口
  ├── schemas.py               ← 数据模型定义 (MedicalRecordState 及子模块)
  ├── mapping.py               ← 路由映射主逻辑 (route_and_transform)
  │     ├── mapping_dicts.py   ← KEY_SYNONYMS / FETUS_FIELD_SYNONYMS
  │     ├── diagnosis_dic.py   ← CATEGORIES_MAPPING (分类关键词词典)
  │     ├── term_dictionary.py ← TERM_REPLACEMENTS (术语规范化)
  │     └── utils.py           ← 工具函数 (日期规范化、孕周推算)
  └── (无 LLM 调用，纯规则引擎)
```

## 四、运行方式

```bash
# 使用默认路径
python stage2_4_after_llm.py

# 指定输入输出
python stage2_4_after_llm.py --input path/to/standard_llm_20.jsonl --output-dir path/to/output --dov 2026-05-20
```
