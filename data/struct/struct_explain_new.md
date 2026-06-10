按照顶层逻辑和第二/三层子节点，我将该数据拆解为 12大核心分类，以下是层次明细及占比说明：

#### **1\. 基本属性与就诊元数据 (6个字段)**

*层级关系：顶层*

用于标识患者基础生理状态及本次门诊/住院就诊的时空节点。

* sessionId: 对话/病历会话唯一标识 ID  
* dov: 就诊日期 (Date of Visit)  
* gwov: 就诊孕周 (Gestational Weeks of Visit)  
* age: 实际年龄  
* eddAge: 预产期年龄  
* bmi: 基础体质指数

#### **2\. 核心孕产指标（顶层 + obh 数组）**

*层级关系：顶层\+ 第二层obh（既往孕产史对象）*

高度浓缩的产妇生育史画像。

* gravidity: 孕次（顶层）  
* parity: 产次（顶层）  
* obh（顶层数组，既往孕产史对象）
  * gravidityindex: 单次妊娠序号  
  * year-month: 年月  
  * AbortionMode流产方式：
    * naturalAbortion: 自然流产  
    * medicalAbortion: 药物流产  
    * surgicalAbortion: 手术流产  
    * currettageAbortion: 刮宫流产 
  * inducedLabor: 引产  
  * fetusdeath: 死胎  
  * preterm: 早产  
  * term: 足月产  
  * deliveryMode分娩方式：
    * vaginalDelivery: 阴道分娩  
    * cesareanSection: 剖宫产  
    * forceps: 产钳助产  
    * vacuumAssisted: 负压吸引助产  
    * breechMidwifery: 臀位助产  
  * postpartum产后情况：
    * hemorrhage: 产后出血  
    * puerperalFever: 产褥热  
  * fetalCount: 胎数  
  * children（数组）
    * childGender: 新生儿性别  
    * childLiving: 新生儿存活  
    * childDeath: 新生儿死亡  
    * childDeathTime: 新生儿死亡时间  
    * childDeathNote: 新生儿死亡备注  
    * neonateWeight: 新生儿体重  
    * sequelaNote: 后遗症备注
  * hospital: 分娩医院  
  * currettage: 清宫  
  * biochemicalAbortion: 生化妊娠  
  * *exceptionalcase: 其他异常情况说明  

#### **3\. 现病史 HPI (9个字段)**

*层级关系：顶层hpi 对象下的第二层节点*

记录本次妊娠的核心进展及就诊主诉。

* hpi(顶层)
  * lmp: 末次月经
  * edd: 预产期  
  * sureEdd: 确认/核对后的预产期  
  * conceiveMode: 受孕方式（自然受孕/辅助生殖等）  
  * conceiveModeNote: 受孕方式的其他备注
  * chiefcomplaint: 核心主诉   
  * *otherNote: 现病史其他文字补充

#### **4\. 既往史 PMH（含备注字段）**

*层级关系：顶层pmh 对象下的第二层节点（布尔/详情复合结构）*

门诊高危建档及住院开立医嘱的重点核查项。

* pmh （顶层）
  * hypertension: 高血压病史  
  * *hypertensionNote: 高血压病史备注  
  * diabetes: 糖尿病史  
  * *diabetesNote: 糖尿病史备注  
  * cardiacDisease: 心脏疾病史  
  * *cardiacDiseaseNote: 心脏疾病史备注  
  * thyroidDisease：甲状腺
  * *thyroidDiseaseNote：甲状腺备注
  * allergyDrug: 药物过敏史（核心排雷项）  
  * *allergyDrugNote: 药物过敏史备注  
  * allergyFood: 食物过敏史  
  * *allergyFoodNote: 食物过敏史备注  
  * allergyOther: 其他过敏史  
  * *allergyOtherNote: 其他过敏史备注  
  * transfusionHistory: 输血史  
  * *transfusionHistoryNote: 输血史备注  
  * operationHistory: 手术史（对评估瘢痕子宫极重要）  
  * *operationHistoryNote: 手术史备注  
  * *otherNote: 既往史其他补充

#### **5\. 月经及婚育史 (8个字段)**

*层级关系：additional\_medical\_history 对象下的第二层节点*

* additional\_medical\_history
  * menarche: 初潮年龄  
  * menstrualCycle: 月经周期  
  * menstrualPeriod: 行经期时长  
  * menstrualVolume: 月经量评估  
  * dysmenorrhea: 痛经史  
  * *dysmenorrheaNote: 痛经史备注  
  * maritalStatus: 婚姻状况  
  * maritalYears: 结婚年限  
  * nearRelation: 近亲婚配史 
  * *nearRelationNote: 近亲婚配史备注
  * *otherNote：月经及婚育史其他补充

#### **6\. 个人史与家族史 (共 9个字段)**

*层级关系：分为 顶层personal\_history (5个) 与 fh (4个) 两个独立对象*

* Personal
  * smoke (吸烟史)
  * *smokeNote (吸烟史备注)
  * alcohol (饮酒史)
  * *alcoholNote (饮酒史备注)
  * hazardoussubstances (有毒物质接触)
  * *hazardoussubstances (有毒物质接触备注)
  * radioactivity (放射物接触)
  * *radioactivity (放射物接触备注)
  * medicine (孕期服药史)  
  * *medicine (孕期服药史备注)  
  * *otherNote：其他
* fh
  * diabetes (家族糖尿病)
  * *diabetesNote (家族糖尿病备注)
  * hypertension (家族高血压)
  * *hypertension (家族高血压备注)
  * birthdefects (出生缺陷史)
  * *birthdefectsNote (出生缺陷史)
  * heritableDisease (遗传病史)
  * *heritableDiseaseNote (遗传病史备注)
  * *otherNote: 其他

#### **7\. 全身体格检查（含体征备注字段）**

*层级关系：顶层physicalExamination 对象下的第二层节点*

这一层级的数据颗粒度极细，是标准的“住院大病历查体”下限，向下兼容门诊常规查体。

* *physicalExamination 
  * **生命体征**: systolic, diastolic, systolic2, diastolic2, systolic3, diastolic3 (支持记录多组血压值), pulse (脉搏), heartrate (心率)  
  * **形态与系统查体**: weight (当前体重), preheight (孕前身高), preweight (孕前体重), bmi (查体时刻BMI)  
  * **器官体征**: skin, thyroid, breast, respiratory, rales, heartrhythm, murmurs, liver, spleen, spine, edema  
    * **器官体征备注**: skinNote, thyroidNote, breastNote, respiratoryNote, ralesNote, heartrhythmNote, murmursNote, liverNote, spleenNote, spineNote, edemaNote  
  * **神经系统**: physiologicalreflection (生理反射), pathologicalreflection (病理反射)  
    * **神经系统备注**: physiologicalreflectionNote, pathologicalreflectionNote  
  * **补充**: otherNote (查体补充说明)

#### **8\. 产科/妇科专科检查 (13个字段)**

*层级关系：gynecologicalExamination对象及其内嵌的 fetusExam (胎儿数组) 第三层节点*

* gynecologicalExamination
  * **母体产检**: fundalHeight (宫高), waistHip (腹围), engagement (胎头入盆/衔接情况)  
  * **妇科查体**: vulva (外阴), vagina (阴道), cervix (宫颈), uterus (子宫形态), adnexa (附件区)  
    * index (多胎序号), fetalHeartRate (胎心率), fetalPosition (胎方位，如LOA), position (胎位，头/臀/横), presentation (先露部位)

#### **9\. 医嘱与诊疗计划 (8个字段)**

*层级关系：advice 对象下的第二层节点*

* advice 
  * prescription: 药品处方开立描述  
  * exam: 检验检查开立描述  
  * appointmentCycle: 随访周期 (如：2周后)  
  * appointmentType: 预约类型 (如：产科专家门诊)  
  * appointmentDate: 预约具体日期  
  * appointmentPeriod: 预约时段 (如：上午)  
  * visitDate: 建议复诊日期  
  * doctorName: 接诊/开嘱医生

# **（暂时剔除部分）**

#### 10. 临床诊断记录 (Diagnoses) — 包含 10 个底层字段

*层级关系：`diagnoses` 对象数组（Array of Objects）* 记录本次门诊或出院的最终确诊结论，支持多诊断并行和排序。

- **诊断核心要素**: `diagnosis` (诊断名称文本，如“妊娠期糖尿病”), `diagnosisCode` (标准ICD编码，如“O24.900”), `highrisk` (高危妊娠布尔标识)
- **时空与状态管理**: `gestationalWeek` (下达诊断时的孕周), `createdDate` (创建时间), `clear` (是否已被清除/作为历史诊断)
- **补充说明与溯源**: `sort` (主次诊断排序序号), `note` (备注/后缀说明), `preNote` (前置修饰语), `outEmrId` (外部病历溯源ID)

#### **11\.  实验室检验大全 (Laboratory Info) — 包含 73 个底层字段（全表最庞大模块）**

*层级关系：`laboratoryInfo` 对象下的第二层平铺节点* 该模块几乎涵盖了国家《孕产妇保健工作规范》中要求的所有必查/备查化验单指标。为了便于理解，我将其内部的 73 个字段划分为以下 **6 个医学亚组**：

1. **夫妇血型与遗传病筛查 (8个字段)**
   - `personalBg` / `partnerBg` (孕妇及丈夫 ABO 血型)
   - `personalRh` / `partnerRh` (双方 Rh 血型)
   - `personalThalassemia` / `partnerThalassemia` (双方地中海贫血筛查结果及备注)
2. **生化、甲功与凝血 (14个字段)**
   - **肝功**: `alt` (谷丙转氨酶), `ast` (谷草转氨酶)
   - **甲功**: `tsh` (促甲状腺激素), `t3`, `t4`
   - **凝血象**: `pt` (凝血酶原时间), `inr`, `aptt`, `tt`, `fib` (纤维蛋白原)
   - **尿液**: `urokinase` (尿蛋白/尿激酶检测)
3. **血液常规与代谢筛查 (6个字段)**
   - `hb` (血红蛋白), `mcv` (平均红细胞体积), `plt` (血小板), `sf` (铁蛋白)
   - `ogttResult` (糖耐量试验结果 - 极高频字段)
   - `g6pdResult` (蚕豆病/G6PD酶结果)
4. **传染病与生殖道感染 (乙肝/丙肝/梅毒/HIV/GBS - 15个字段)**
   - **乙肝五项及DNA**: `hbsag`, `hbsab`, `hbeag`, `hbeab`, `hbcab`, `hbvResult`, `hbvdna`
   - **其他传染病**: `hcvResult`, `hcvrnaResult` (丙肝), `syphilisResult` (梅毒), `hivResult` (艾滋), `gbsResult` (B族链球菌)
5. **产前筛查与胎儿诊断 (4个字段)**
   - `downsScreenEarly` (早孕期唐筛), `downsScreenMiddle` (中孕期唐筛), `nipt` (无创DNA), `prenatalDiagnosisResult` (羊水穿刺等产前诊断结果)
6. **检验异常警戒标识（Sign 标识位 - 22个字段）**
   - 系统为几乎所有的核心化验单配备了 `*Sign` 布尔字段（如 `tshSign`, `hbSign`, `ogttResultSign`, `niptSign` 等）。一旦异常，该标识位亮起，直接触发产科高危评分预警。

#### 12.产科专属超声阵列 (Ultrasounds) — 包含 3 大阵列及下属字段

*层级关系：顶层的三个独立对象数组（Array of Objects）* 产科高度依赖超声，这里按孕期阶段拆分了最核心的三大超声节点。

- **`ntExams` (早孕期 NT 超声阵列 - 包含 6 个字段)**:
  - `nt` (颈项透明层厚度数值), `crl` (头臀长), `gestationalWeek` (超声孕周), `menopause` (停经天数), `checkdate`, `reportdate` (检查与报告日期)
- **`nfExams` (孕中期 NF 超声阵列)**: 记录孕中期胎儿颈部皱褶厚度等测值。
- **`mlUltrasounds` (中晚孕期形态学超声阵列)**: 即俗称的“大排畸/小排畸”，记录胎儿解剖结构的精细测量。