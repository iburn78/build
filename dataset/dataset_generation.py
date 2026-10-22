from build.models.profile import Profile
from build.models.component import Component
from build.models.valuechain import ValueChain
import sys
# sys.exit()

# Profiles do not need to exist before components are created.
# Components must exist before value chains are created.

# --------------------------------------------------
# AI
# --------------------------------------------------
ValueChain.get_item(
key="AI", 
components=[
Component.get_item('메모리', namelist = ['하이닉스', '삼성전자(A)']),
Component.get_item('후공정 검사장비', namelist=['쎄크']),
Component.get_item('전력 제품', namelist = ['비엠티']),
Component.get_item('메모리 기판', namelist=['LG이노텍(B)', '삼성전기', '티엘비', '심텍', '해성디에스', '대덕전자']),
Component.get_item('PCB 기판', namelist=['이수페타시스']),
Component.get_item('MLCC', namelist=['삼성전기', '삼화콘덴서']),
])

# --------------------------------------------------
# AIDC
# --------------------------------------------------
ValueChain.get_item(
key="AI 데이터센터", 
components=[
Component.get_item('커패시터', namelist = ['LS머트리얼즈(A)', '비나텍']), 
Component.get_item('버스덕트', namelist = ['가온전선']),
Component.get_item('광증폭기', namelist = ['라이콤']),
Component.get_item('광케이블', namelist = ['대한광통신']),
Component.get_item('ESS 냉각시스템', namelist = ['한중엔시에스']),
Component.get_item('가스터빈', namelist = ['덕산네오룩스(B)']),
# Component.get_item('산업용 열교환기', namelist = ['디티에스']), # 상장예정
])

# --------------------------------------------------
# 전자 부품
# --------------------------------------------------
ValueChain.get_item(
key = "전자 부품",
components=[
Component.get_item('스마트글래스', namelist=['사피엔반도체']),
Component.get_item('카메라 모듈', namelist=['LG이노텍(A)', '삼성전기', '엠씨넥스', '세코닉스']),
Component.get_item('Display', namelist=['덕산네오룩스(A)', '이녹스첨단소재', '피엔에이치테크', 'PI첨단소재', 'LX세미콘']),
Component.get_item('폴더블', namelist=['KH바텍', '세경하이테크', '파인엠텍']),
])

# --------------------------------------------------
# EV_Battery
# --------------------------------------------------
ValueChain.get_item(
key='EV 배터리',
components=[
Component.get_item('동박', namelist=['SKC(A)', '롯데에너지머티리얼즈', '솔루스첨단소재']),
Component.get_item('배터리 분리막', namelist=['SK아이이테크놀로지', '더블유씨피']),
Component.get_item('배터리 셀', namelist=['LG에너지솔루션', '삼성SDI', 'SK이노베이션(C)']),
Component.get_item('양극재', namelist=['에코프로비엠', '포스코퓨처엠', '엘앤에프', 'LG화학', '코스모신소재']),
Component.get_item('음극재', namelist=['포스코퓨처엠', '대주전자재료']),
Component.get_item('전고체', namelist=['효성티앤씨', '레이크머티리얼즈', '한농화성']),
Component.get_item('전구체', namelist=['에코프로머티', '에코앤드림']),
Component.get_item('전해질', namelist=['엔켐', '동화기업(C)', '솔브레인홀딩스', '덕산테코피아']),
])

# --------------------------------------------------
# Chemicals
# --------------------------------------------------
ValueChain.get_item(
key='화학',
components=[
Component.get_item('정밀 화학', namelist=['한농화성']),
])

# --------------------------------------------------
# Financial institutions
# --------------------------------------------------
ValueChain.get_item(
key='금융업',
components=[
Component.get_item('은행', namelist = ['KB금융', '신한지주', '하나금융지주', '우리금융지주', 'BNK금융지주', 'iM금융지주', 'JB금융지주', '기업은행', '제주은행', '카카오뱅크']),
Component.get_item('증권사', namelist=['미래에셋증권', '한국금융지주', 'NH투자증권', '삼성증권', '키움증권', '대신증권', '한화투자증권', '유안타증권', '교보증권', '현대차증권', '신영증권', '유진투자증권', '부국증권', '한양증권', 'SK증권', 'DB증권', '다올투자증권', '상상인증권']),
])


# --------------------------------------------------
# Bio
# --------------------------------------------------
ValueChain.get_item(
key='메디컬 바이오', 
components=[
Component.get_item('메디컬 에스테틱', namelist = ['휴젤', '파마리서치', '메디톡스', '휴메딕스', '제테마', '녹십자웰빙']), # 미용 의료 시술 소재
Component.get_item('에스테틱 의료기기', namelist = ['클래시스', '원텍']),
Component.get_item('바이오시밀러', namelist=['셀트리온', '삼성에피스홀딩스']),
Component.get_item('바이오의약품 위탁생산', namelist=['삼성바이오로직스(A)']), # CDMO
Component.get_item('화장품 ODM', namelist=['코스맥스', '한국콜마']),
])

# --------------------------------------------------
# 뷰티
# --------------------------------------------------
ValueChain.get_item(
key='K 뷰티', 
components=[
Component.get_item('화장품 용기 제조', namelist=['펌텍코리아']),
])

# --------------------------------------------------
# 가전
# --------------------------------------------------
Component.get_item('가전', namelist = ['삼성전자(C)', 'LG전자(A)', '코웨이'])

