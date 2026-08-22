from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict


class StatusDetail(BaseModel):
    status: int = Field(default=-1, description="-1:未提及, 0:否认, 1:承认")
    details: Optional[str] = None


class OBHChild(BaseModel):
    childGender: Optional[int] = None
    childLiving: int = Field(default=-1, description="-1:未提及, 0:否, 1:是")
    childDeath: int = Field(default=-1, description="-1:未提及, 0:否, 1:是")
    childDeathTime: Optional[str] = None
    childDeathNote: Optional[str] = None
    neonateWeight: Optional[str] = None
    sequelaNote: Optional[str] = None

    @field_validator('childLiving', 'childDeath', mode='before')
    def normalize_tristate(cls, v):
        # Java 端只接受 int 三状态，兼容历史 bool/None 入参
        if v is None:
            return -1
        if isinstance(v, bool):
            return 1 if v else 0
        return v


class OBHEntry(BaseModel):
    gravidityindex: Optional[int] = None
    year: Optional[str] = None
    month: Optional[str] = None
    vaginalDelivery: Optional[int] = None
    cesareanSection: Optional[int] = None
    naturalAbortion: Optional[int] = None
    medicalAbortion: Optional[int] = None
    surgicalAbortion: Optional[int] = None
    currettageAbortion: Optional[int] = None
    currettage: Optional[int] = None
    biochemicalAbortion: Optional[int] = None
    inducedLabor: Optional[int] = None
    fetusdeath: Optional[int] = None
    preterm: Optional[int] = None
    term: Optional[int] = None
    forceps: Optional[int] = None
    vacuumAssisted: Optional[int] = None
    breechMidwifery: Optional[int] = None
    hemorrhage: Optional[int] = None
    puerperalFever: Optional[int] = None
    fetalcount: Optional[int] = None
    hospital: Optional[str] = None
    exceptionalcase: Optional[str] = None
    children: List[OBHChild] = Field(default_factory=list)


class HPI(BaseModel):
    lmp: Optional[str] = None
    edd: Optional[str] = None
    sureEdd: Optional[str] = None
    conceiveMode: Optional[str] = None
    conceiveModeNote: Optional[str] = None
    chiefcomplaint: Optional[str] = None
    otherNote: Optional[str] = None


class PMH(BaseModel):
    hypertension: StatusDetail = Field(default_factory=StatusDetail)
    hypertensionNote: Optional[str] = None
    diabetes: StatusDetail = Field(default_factory=StatusDetail)
    diabetesNote: Optional[str] = None
    cardiacDisease: StatusDetail = Field(default_factory=StatusDetail)
    cardiacDiseaseNote: Optional[str] = None
    thyroidDisease: StatusDetail = Field(default_factory=StatusDetail)
    thyroidDiseaseNote: Optional[str] = None
    operationHistory: StatusDetail = Field(default_factory=StatusDetail)
    operationHistoryNote: Optional[str] = None
    allergyDrug: StatusDetail = Field(default_factory=StatusDetail)
    allergyDrugNote: Optional[str] = None
    allergyFood: StatusDetail = Field(default_factory=StatusDetail)
    allergyFoodNote: Optional[str] = None
    allergyOther: StatusDetail = Field(default_factory=StatusDetail)
    allergyOtherNote: Optional[str] = None
    transfusionHistory: StatusDetail = Field(default_factory=StatusDetail)
    transfusionHistoryNote: Optional[str] = None
    otherNote: Optional[str] = None

# 【补充缺失的类】：月经及婚育史
class AdditionalHistory(BaseModel):
    menarche: Optional[int] = None
    menstrualCycle: Optional[str] = None
    otherNote: Optional[str] = None
    menstrualPeriod: Optional[int] = None
    menstrualVolume: Optional[str] = None
    dysmenorrhea: StatusDetail = Field(default_factory=StatusDetail)
    dysmenorrheaNote: Optional[str] = None
    maritalStatus: Optional[str] = None
    maritalYears: Optional[int] = None
    nearRelation: StatusDetail = Field(default_factory=StatusDetail)
    nearRelationNote: Optional[str] = None


class PersonalHistory(BaseModel):
    smoke: StatusDetail = Field(default_factory=StatusDetail)
    smokeNote: Optional[str] = None
    alcohol: StatusDetail = Field(default_factory=StatusDetail)
    alcoholNote: Optional[str] = None
    hazardoussubstances: StatusDetail = Field(default_factory=StatusDetail)
    hazardoussubstancesNote: Optional[str] = None
    radioactivity: StatusDetail = Field(default_factory=StatusDetail)
    radioactivityNote: Optional[str] = None
    medicine: StatusDetail = Field(default_factory=StatusDetail)
    medicineNote: Optional[str] = None
    otherNote: Optional[str] = None


class FamilyHistory(BaseModel):
    diabetes: StatusDetail = Field(default_factory=StatusDetail)
    diabetesNote: Optional[str] = None
    hypertension: StatusDetail = Field(default_factory=StatusDetail)
    hypertensionNote: Optional[str] = None
    birthdefects: StatusDetail = Field(default_factory=StatusDetail)
    birthdefectsNote: Optional[str] = None
    heritableDisease: StatusDetail = Field(default_factory=StatusDetail)
    heritableDiseaseNote: Optional[str] = None
    otherNote: Optional[str] = None


class PhysicalExam(BaseModel):
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    preheight: Optional[float] = None
    preweight: Optional[float] = None
    otherNote: Optional[str] = None
    systolic2: Optional[int] = None
    diastolic2: Optional[int] = None
    systolic3: Optional[int] = None
    diastolic3: Optional[int] = None
    pulse: Optional[int] = None
    heartrate: Optional[int] = None
    weight: Optional[float] = None
    bmi: Optional[float] = None
    skin: StatusDetail = Field(default_factory=StatusDetail)
    skinNote: Optional[str] = None
    thyroid: StatusDetail = Field(default_factory=StatusDetail)
    thyroidNote: Optional[str] = None
    breast: StatusDetail = Field(default_factory=StatusDetail)
    breastNote: Optional[str] = None
    respiratory: StatusDetail = Field(default_factory=StatusDetail)
    respiratoryNote: Optional[str] = None
    rales: StatusDetail = Field(default_factory=StatusDetail)
    ralesNote: Optional[str] = None
    heartrhythm: StatusDetail = Field(default_factory=StatusDetail)
    heartrhythmNote: Optional[str] = None
    murmurs: StatusDetail = Field(default_factory=StatusDetail)
    murmursNote: Optional[str] = None
    liver: StatusDetail = Field(default_factory=StatusDetail)
    liverNote: Optional[str] = None
    spleen: StatusDetail = Field(default_factory=StatusDetail)
    spleenNote: Optional[str] = None
    spine: StatusDetail = Field(default_factory=StatusDetail)
    spineNote: Optional[str] = None
    physiologicalreflection: StatusDetail = Field(default_factory=StatusDetail)
    physiologicalreflectionNote: Optional[str] = None
    pathologicalreflection: StatusDetail = Field(default_factory=StatusDetail)
    pathologicalreflectionNote: Optional[str] = None
    edema: StatusDetail = Field(default_factory=StatusDetail)
    edemaNote: Optional[str] = None

    @field_validator('preweight')
    def validate_weight(cls, v):
        if v is not None and (v < 30.0 or v > 150.0): return None
        return v


# 【补充缺失的类】：产科/妇科专科检查
class GynecologicalExam(BaseModel):
    fundalHeight: Optional[float] = None
    engagement: Optional[str] = None
    otherNote: Optional[str] = None
    waistHip: Optional[float] = None
    vulva: Optional[str] = None
    vagina: Optional[str] = None
    cervix: Optional[str] = None
    uterus: Optional[str] = None
    adnexa: Optional[str] = None
    fetusExam: List["FetusExam"] = Field(default_factory=list)


class FetusExam(BaseModel):
    index: int = Field(..., description="胎儿序号")
    fetalHeartRate: Optional[int] = None
    fetalPosition: Optional[str] = None
    position: Optional[str] = None
    presentation: Optional[str] = None


class Advice(BaseModel):
    prescription: Optional[str] = Field(default=None, description="药品处方描述")
    exam: Optional[str] = Field(default=None, description="检验检查描述")
    appointmentCycle: Optional[int] = None
    appointmentType: Optional[str] = None
    appointmentDate: Optional[str] = None
    appointmentPeriod: Optional[str] = None
    visitDate: Optional[str] = None
    doctorName: Optional[str] = None


class MedicalRecordState(BaseModel):
    # 1. 基本属性与就诊元数据 (顶层)
    sessionId: str
    dov: Optional[str] = None
    gwov: Optional[str] = None
    age: Optional[int] = None
    eddAge: Optional[int] = None
    bmi: Optional[float] = None
    gravidity: Optional[int] = None
    parity: Optional[int] = None

    # 子模块
    obh: List[OBHEntry] = Field(default_factory=list)
    hpi: HPI = Field(default_factory=HPI)
    pmh: PMH = Field(default_factory=PMH)
    additional_medical_history: AdditionalHistory = Field(default_factory=AdditionalHistory)
    personal_history: PersonalHistory = Field(default_factory=PersonalHistory)
    fh: FamilyHistory = Field(default_factory=FamilyHistory)
    physicalExamination: PhysicalExam = Field(default_factory=PhysicalExam)
    gynecologicalExamination: GynecologicalExam = Field(default_factory=GynecologicalExam)
    fetusExam: Dict[int, FetusExam] = Field(default_factory=dict)
    advice: Advice = Field(default_factory=Advice)

    def to_output_dict(self):
        data = self.model_dump()
        fetus_list = list(data['fetusExam'].values())
        data['gynecologicalExamination']['fetusExam'] = fetus_list
        data.pop('fetusExam', None)
        return data