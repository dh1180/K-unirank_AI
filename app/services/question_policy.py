"""Ground explicit user constraints before trusting model output. No admission predictions."""
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path


class QuestionClarification(Exception):
    pass


class MissingGrade(QuestionClarification):
    pass


REGIONS = {
    "서울": "서울", "서울특별시": "서울", "경기": "경기", "경기도": "경기",
    "인천": "인천", "인천광역시": "인천", "부산": "부산", "부산광역시": "부산",
    "대구": "대구", "대구광역시": "대구", "광주": "광주", "광주광역시": "광주",
    "대전": "대전", "대전광역시": "대전", "울산": "울산", "울산광역시": "울산",
    "세종": "세종", "세종특별자치시": "세종", "강원": "강원", "강원도": "강원", "강원특별자치도": "강원",
    "충북": "충북", "충청북도": "충북", "충남": "충남", "충청남도": "충남",
    "전북": "전북", "전라북도": "전북", "전북특별자치도": "전북", "전남": "전남", "전라남도": "전남",
    "경북": "경북", "경상북도": "경북", "경남": "경남", "경상남도": "경남", "제주": "제주", "제주특별자치도": "제주",
}
REGION_ORDER = list(dict.fromkeys(REGIONS.values()))
MAJORS = {
    "컴공": "컴퓨터,소프트웨어,컴퓨팅", "간호": "간호", "심리": "심리", "경영": "경영",
    "소프트웨어": "소프트웨어", "컴퓨터": "컴퓨터", "기계": "기계", "전자": "전자",
    "전기": "전기", "화학": "화학", "생명": "생명", "건축": "건축", "디자인": "디자인",
    "유아교육": "유아교육", "사회복지": "사회복지", "물리치료": "물리치료",
    "의대": "의예,의학과,의학부", "치대": "치의예,치의학", "한의대": "한의예,한의학",
    "약대": "약학", "수의대": "수의예,수의학",
}
NEGATION = r"\s*(?:학과|학부)?\s*(?:은|는|을|를)?\s*(?:말고|제외|빼고|아닌)"


def mentions(text, aliases):
    """Longest non-overlapping literal matches; avoid 서울 in 서울특별시, 의대 in 수의대."""
    pattern = "|".join(re.escape(x) for x in sorted(aliases, key=len, reverse=True))
    return list(re.finditer(pattern, text, re.IGNORECASE)) if pattern else []


def negated(text, end):
    return bool(re.match(NEGATION, text[end:]))


# These are query aliases, never a ranking or a claim of equivalent admission standards.
# KNU10 membership: https://iei.jbnu.ac.kr/iei/31360/subview.do
# Colloquial regional group excludes Seoul; explicit KNU10 includes it.
REGIONAL_FLAGSHIPS = (
    "강원대학교", "경북대학교", "경상국립대학교", "부산대학교", "전남대학교",
    "전북대학교", "제주대학교", "충남대학교", "충북대학교",
)
UNIVERSITY_GROUPS = {
    "건동홍": ("건국대학교", "동국대학교", "홍익대학교"),
    "서성한": ("서강대학교", "성균관대학교", "한양대학교"),
    "중경외시": ("중앙대학교", "경희대학교", "한국외국어대학교", "서울시립대학교"),
    "국숭세단": ("국민대학교", "숭실대학교", "세종대학교", "단국대학교 죽전캠퍼스"),
    "광명상가": ("광운대학교", "명지대학교 인문캠퍼스", "명지대학교 자연캠퍼스", "상명대학교", "가톨릭대학교"),
    "한서삼": ("한성대학교", "서경대학교", "삼육대학교"),
    "서연고": ("서울대학교", "연세대학교", "고려대학교"),
    "sky": ("서울대학교", "연세대학교", "고려대학교"),
    **dict.fromkeys(("지거국", "지방거점국립대", "지방거점국립대학", "지방거점국립대학교",
                     "지역거점국립대", "지역거점국립대학", "지역거점국립대학교"), REGIONAL_FLAGSHIPS),
    **dict.fromkeys(("거점국립대", "거점국립대학", "거점국립대학교",
                     "국가거점국립대", "국가거점국립대학", "국가거점국립대학교", "knu10"),
                    ("서울대학교", *REGIONAL_FLAGSHIPS)),
}
UNIVERSITY_SHORT_NAMES = {
    "건대": ("건국대학교",), "홍대": ("홍익대학교",),
    "건국": ("건국대학교",), "동국": ("동국대학교",), "홍익": ("홍익대학교",),
    "한양대에리카": ("한양대학교 ERICA캠퍼스",),
    "동국대와이즈": ("동국대학교 WISE캠퍼스",),
    "건국대충주": ("건국대학교 글로컬캠퍼스",),
    "중대": ("중앙대학교",), "성대": ("성균관대학교",),
    "외대": ("한국외국어대학교",), "한국외대": ("한국외국어대학교",),
    "시립대": ("서울시립대학교",), "과기대": ("서울과학기술대학교",),
    "서울과기대": ("서울과학기술대학교",), "항공대": ("한국항공대학교",),
    "성균관대": ("성균관대학교",), "이화여대": ("이화여자대학교",),
    "숙명여대": ("숙명여자대학교",), "성신여대": ("성신여자대학교",),
    "서울여대": ("서울여자대학교",), "동덕여대": ("동덕여자대학교",),
    "덕성여대": ("덕성여자대학교",),
    "명지대": ("명지대학교 인문캠퍼스", "명지대학교 자연캠퍼스"),
    "명지대학교": ("명지대학교 인문캠퍼스", "명지대학교 자연캠퍼스"),
    "단국대": ("단국대학교 죽전캠퍼스", "단국대학교 천안캠퍼스"),
    "단국대학교": ("단국대학교 죽전캠퍼스", "단국대학교 천안캠퍼스"),
    "경상대": ("경상국립대학교",),
    "부경대": ("국립부경대학교",),
}


@lru_cache(maxsize=1)
def university_aliases():
    names = json.loads((Path(__file__).parent.parent / "university_names.json").read_text(encoding="utf-8"))
    aliases = {}
    for name in names:
        aliases[name.replace(" ", "").lower()] = (name,)
        short = name.replace("대학교", "대").replace(" ", "").lower()
        if len(short) >= 3:
            aliases[short] = (name,)
            if short.endswith("캠퍼스"):
                aliases[short.removesuffix("캠퍼스")] = (name,)
                aliases[name.replace(" ", "").lower().removesuffix("캠퍼스")] = (name,)
    for short, members in (UNIVERSITY_SHORT_NAMES | UNIVERSITY_GROUPS).items():
        if not set(members).issubset(names):
            raise RuntimeError("대학 별칭 카탈로그를 확인해 주세요.")
        aliases[short] = members
    return aliases


def university_mentions(question):
    aliases = university_aliases()
    compact = re.sub(r"\s+", "", question).lower()
    found, masked = [], compact
    for match in mentions(compact, aliases):
        tail = re.sub(r"^(?:라인|대학군|그룹)", "", compact[match.end():])
        if negated(tail, 0):
            raise QuestionClarification("대학 제외 조건은 아직 지원하지 않습니다. 확인할 대학 이름을 직접 지정해 주세요.")
        if match.group() in UNIVERSITY_GROUPS and re.match(r"(?:라인)?(?:이상|이하|보다|급|정도)", tail):
            raise QuestionClarification("대학군의 위아래를 임의의 순위로 해석하지 않습니다. 검색할 대학군이나 대학을 직접 지정해 주세요.")
        found.extend(aliases[match.group()])
        masked = masked[:match.start()] + " " * (match.end()-match.start()) + masked[match.end():]
    def already_recognized(start, end):
        compact_start = len(re.sub(r"\s+", "", question[:start]))
        compact_end = len(re.sub(r"\s+", "", question[:end]))
        return not masked[compact_start:compact_end].strip()

    for candidate_match in re.finditer(r"(?:^|\s)([가-힣A-Za-z]{2,20}(?:대학교|대학|대))(?=\s|[,·/]|에서|의|를|으로|$)", question):
        candidate = candidate_match.group(1)
        if already_recognized(*candidate_match.span(1)):
            continue
        if candidate.lower() not in aliases and candidate not in MAJORS and candidate not in {"전체대학", "모든대학", "어느대학", "수도권대학", "서울권대학", "국립대", "사립대", "전문대"}:
            residue = candidate.lower()
            for match in reversed(mentions(residue, aliases)):
                residue = residue[:match.start()] + " " * (match.end()-match.start()) + residue[match.end():]
            residue = re.sub(r"이랑|하고|랑|와|과|및|또는|그리고|\s", "", residue)
            if residue:
                raise QuestionClarification("대학 이름을 확인해 주세요. 등록된 정확한 대학명으로 검색할 수 있습니다.")
    # Suggest a clarification for close spellings; never silently correct to a different university.
    for candidate_match in re.finditer(r"[가-힣A-Za-z]{2,20}", question.lower()):
        if already_recognized(*candidate_match.span()):
            continue
        candidate = candidate_match.group()
        token = re.sub(r"(?:중에서는|중에서|에서는|에서|으로|까지|하고|이랑|랑|와|과|만|도|를|을|은|는|의)$", "", candidate)
        if token in aliases or token in REGIONS or token in MAJORS or token in {"수도권", "인서울", "대학", "학과", "내신", "전체", "전국"}:
            continue
        group_typos = [group for group in UNIVERSITY_GROUPS
                       if len(group) == len(token) and sum(a != b for a, b in zip(group, token)) == 1]
        near = group_typos[:1] or get_close_matches(token, aliases, n=1, cutoff=0.8)
        if near and len(token) <= 8:
            raise QuestionClarification(f"'{candidate}'의 대학 조건을 확인해 주세요. '{near[0]}'을 뜻했다면 해당 이름으로 다시 입력해 주세요.")
    found = list(dict.fromkeys(found))
    if len(found) > 10 or len(",".join(found)) > 160:
        raise QuestionClarification("한 번에 대학 10곳까지 지정해 주세요.")
    return ",".join(found) or None, masked


@dataclass
class ExplicitQuestion:
    grade: Decimal
    year: int | None
    track: str
    region: str | None
    major: str | None
    university: str | None
    special: str
    scope: str
    notes: list[str]

    @classmethod
    def read(cls, question):
        if re.search(r"정시|평백|백분위|표준점수", question):
            raise QuestionClarification("현재 AI 검색은 9등급제 내신의 수시 교과·종합 입결 비교를 지원합니다. 정시·백분위는 입결 찾기에서 확인해 주세요.")
        if re.search(r"5\s*등급\s*제|성취도|[ABCDE]\s*등급", question, re.IGNORECASE):
            raise QuestionClarification("현재 자료는 9등급제 내신 기준입니다. 5등급제·성취도를 임의로 환산하지 않습니다.")
        if re.search(r"등급\s*(?:초반|중반|후반|대(?:인데|로|에서|\s|$))|(?<![\d.])[1-9](?:\.\d+)?\s*[~∼-]\s*[1-9](?:\.\d+)?\s*등급", question):
            raise MissingGrade("등급대 대신 정확한 평균등급을 알려주세요. 예: 내신 3.25등급")
        normalized = re.sub(r"([1-9])\s*점\s*(\d{1,2})(?!\d)", r"\1.\2", question)
        primary = re.findall(r"(?:내신|평균등급|평균)\s*(?:평균)?\s*(?:등급)?\s*(?:이|은|는|:)?\s*([1-9](?:\.\d{1,2})?)(?![\d.])", normalized)
        fallback = re.findall(r"(?<![\d.])([1-9](?:\.\d{1,2})?)\s*등급(?!\s*제)", normalized)
        grades = {Decimal(x) for x in primary or fallback}
        if not grades:
            raise MissingGrade("내신 평균등급을 알려주세요. 예: 내신 3.25등급 서울 간호학과")
        if len(grades) != 1:
            raise MissingGrade("여러 내신 등급이 입력되었습니다. 비교할 본인의 평균등급 하나만 알려주세요.")
        grade = grades.pop()
        if grade < 1 or grade > 9:
            raise MissingGrade("내신 평균등급은 1.00~9.00 범위로 입력해 주세요.")
        years = set(re.findall(r"(?<!\d)(20\d{2})(?!\d)", question))
        if len(years)>1:
            raise QuestionClarification("비교할 입결 학년도를 하나만 지정해 주세요.")
        year = int(next(iter(years))) if years else None
        if year and year>2100:
            raise QuestionClarification("입결 학년도를 확인해 주세요.")
        tracks = set()
        negative_track = False
        for m in mentions(question, ["학생부교과", "학생부종합", "학종", "교과", "종합"]):
            if negated(question,m.end()):
                negative_track = True
                continue
            tracks.add("holistic" if m.group() in {"학생부종합","학종","종합"} else "student")
        if negative_track and not tracks:
            raise QuestionClarification("비교할 전형을 직접 지정해 주세요. 예: 학생부종합")
        if len(tracks)>1:
            raise QuestionClarification("학생부교과와 학생부종합 중 비교할 전형 하나를 선택해 주세요.")
        university, masked = university_mentions(question)
        # Recognized groups are exact university lists, not an unsupported ownership filter.
        if re.search(r"국립(?:대(?:학(?:교)?)?)?\s*만", masked) or re.search(r"사립.*제외|전문대|수능최저|면접.*(?:없|제외)|여대.*제외|등록금|기숙사|취업률", question):
            raise QuestionClarification("이 검색은 지역·대학·학과·내신·교과/종합 조건을 비교합니다. 대학 유형·최저·면접·등록금 조건은 대학 정보와 모집요강에서 확인해 주세요.")
        special_terms = r"농어촌|기회균등|기회균형|지역인재|특성화고|특별전형"
        if re.search(rf"(?:{special_terms})\s*(?:전형)?\s*만",question):
            raise QuestionClarification("특별전형만 지정하는 검색은 입결 찾기를 이용해 주세요. 일반 전형과 함께 보려면 '특별전형 포함'이라고 입력해 주세요.")
        special = "all" if re.search(rf"(?:{special_terms}).{{0,8}}포함", question) else "exclude"
        region_aliases = dict(REGIONS)
        region_aliases["수도권"] = "서울,경기,인천"
        region_aliases["인서울"] = "서울"
        positive, excluded = set(), set()
        for m in mentions(masked, region_aliases):
            values = set(region_aliases[m.group()].split(","))
            (excluded if negated(masked,m.end()) else positive).update(values)
        if "전국" in masked: positive.update(REGION_ORDER)
        regions = ((positive or set(REGION_ORDER)) if excluded else positive) - excluded
        if (positive or excluded) and not regions:
            raise QuestionClarification("지정한 지역과 제외 지역이 겹칩니다. 검색할 지역을 다시 지정해 주세요.")
        if re.search(r"(?:서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)[,·/](?:서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)(?:제외|말고|빼고)", masked):
            raise QuestionClarification("제외할 지역을 각각 적어 주세요. 예: 서울 제외, 경기 제외")
        region = ",".join(r for r in REGION_ORDER if r in regions) if regions and regions!=set(REGION_ORDER) else None
        major_terms, notes = [], []
        compact_question = re.sub(r"\s+", "", question).lower()
        # Use the same longest matches as university_mentions: nested names must not add
        # a conflicting larger group (e.g. 지방거점국립대 must never include Seoul).
        matched_groups = dict.fromkeys(m.group() for m in mentions(compact_question, university_aliases())
                                       if m.group() in UNIVERSITY_GROUPS)
        for alias in matched_groups:
            members = UNIVERSITY_GROUPS[alias]
            scope_note = " (서울대 제외·기본 대학 항목 기준)" if members == REGIONAL_FLAGSHIPS else ""
            notes.append(f"{alias.upper() if alias in {'sky', 'knu10'} else alias}{scope_note}은 {'·'.join(members)} 조건으로 검색했습니다.")
        if university and any("캠퍼스" in name for name in university.split(",")):
            notes.append("캠퍼스는 결과의 대학 이름으로 구분했습니다. 특정 캠퍼스만 보려면 캠퍼스 이름까지 입력해 주세요.")
        negative_major = False
        for m in mentions(masked, MAJORS):
            if negated(masked,m.end()): negative_major=True;continue
            major_terms.extend(MAJORS[m.group()].split(","))
            if m.group()=="컴공":notes.append("컴공은 컴퓨터·소프트웨어·컴퓨팅 관련 모집단위로 함께 검색했습니다.")
        if negative_major and not major_terms:
            raise QuestionClarification("학과 제외 대신 관심 있는 학과 이름을 직접 지정해 주세요.")
        if len(set(major_terms))>5:
            raise QuestionClarification("관련 학과 검색어는 한 번에 5개까지 지정해 주세요.")
        if not major_terms:
            raw = re.findall(r"(?:^|\s)([가-힣A-Za-z]{2,20}(?:학과|학부))",question)
            major_terms = [x[:-1] if x.endswith("학과") else x for x in raw if x not in {"전체학과","모든학과","갈만한학과","지원가능한학과","추천학과"} and not negated(question, question.find(x)+len(x))]
        return cls(grade,year,next(iter(tracks),"student"),region,",".join(dict.fromkeys(major_terms)) or None,
                   university,special,"all" if re.search(r"전체\s*(?:등급|입결)|등급\s*범위\s*전체",question) else "near",notes)

    def resolve(self, raw, question, limit):
        # Explicit numeric values/regions/tracks always win over a model guess.
        major = self.major
        if major is None and raw.get("major"):
            terms = [x.strip() for x in str(raw["major"]).split(",") if x.strip()]
            if self.university:
                aliases = university_aliases()
                selected = set(self.university.split(","))
                terms = [x for x in terms if x not in selected and not (
                    x.replace(" ", "").lower() in aliases
                    and set(aliases[x.replace(" ", "").lower()]).issubset(selected))]
            terms = [x for x in terms if x not in {"학과", "갈만한 학과", "갈만한학과", "추천학과", "전체학과", "전체 학과"}]
            if len(terms)>5 or any(x not in question for x in terms):
                raise QuestionClarification("학과 이름을 명확히 적어 주세요. 입력하지 않은 학과로 검색하지 않습니다.")
            major = ",".join(terms) or None
        return {"grade":self.grade,"year":self.year,"track":self.track,"special":self.special,
                "scope":self.scope,"region":self.region,"major":major,"university":self.university,
                "notes":list(dict.fromkeys(self.notes)),"limit":limit}

    def fallback(self, question, limit):
        if not (self.major or self.university):
            raise QuestionClarification("질문 해석이 지연되고 있습니다. 관심 학과나 대학 이름을 함께 입력해 주세요.")
        return self.resolve({},question,limit)
