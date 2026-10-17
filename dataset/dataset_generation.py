from build.models.component import Component
from build.models.valuechain import ValueChain

# '''
# ==================================================
# profiles do not need to be created before components' creation
# components should be already created for valuechain to be created
# --------------------------------------------------
# 메모리
# --------------------------------------------------
Component.get_item('메모리', namelist = ['하이닉스', '삼성전자(A)'])
Component.get_item('후공정 검사장비', namelist=['쎄크'])
# --------------------------------------------------
# 가전
# --------------------------------------------------
Component.get_item('가전', namelist = ['삼성전자', 'LG전자'])
Component.get_item('가전 렌탈', namelist=['코웨이'])

# --------------------------------------------------
# 전자 부품
# --------------------------------------------------
cp_list = []
cp_list.append(Component.get_item('스마트글래스', namelist = ['사피엔반도체']))
cp_list.append(Component.get_item('카메라 모듈', namelist = ['LG이노텍(A)', '삼성전기', '엠씨넥스', '세코닉스']))
cp_list.append(Component.get_item('메모리 기판', namelist = ['LG이노텍(B)', '삼성전기', '티엘비', '심텍', '해성디에스', '대덕전자'])) # PCB, FPCB
cp_list.append(Component.get_item('PCB 기판', namelist = ['이수페타시스']))
cp_list.append(Component.get_item('MLCC', namelist = ['삼성전기', '삼화콘덴서']))
cp_list.append(Component.get_item('Display', namelist = ['덕산네오룩스', '이녹스첨단소재', '피엔에이치테크', 'PI첨단소재', 'LX세미콘']))
cp_list.append(Component.get_item('폴더블', namelist = ['KH바텍', '세경하이테크', '파인엠텍']))

vc = ValueChain.get_item(
    key = "전자 부품",
    component_keys=[cp.key for cp in cp_list],
)

# --------------------------------------------------
# EV_Battery
# --------------------------------------------------
Component.get_item('동박', namelist=['SKC', '롯데에너지머티리얼즈', '솔루스첨단소재'])
Component.get_item('분리막', namelist=['SK아이이테크놀로지', '더블유씨피'])
Component.get_item('셀', namelist=['LG에너지솔루션', '삼성SDI', 'SK이노베이션(C)'])
Component.get_item('양극재', namelist=['에코프로비엠', '포스코퓨처엠', '엘앤에프', 'LG화학', '코스모신소재'])
Component.get_item('음극재', namelist=['포스코퓨처엠', '대주전자재료'])
Component.get_item('전고체', namelist=['효성티앤씨', '레이크머티리얼즈', '한농화성'])
Component.get_item('전구체', namelist=['에코프로머티', '에코앤드림'])
Component.get_item('전해질', namelist=['엔켐', '동화기업', '솔브레인홀딩스', '덕산테코피아'])

vc = ValueChain.get_item(
    key='EV 배터리',
    component_keys=['동박', '분리막', '셀', '양극재', '음극재', '전고체', '전구체', '전해질'],
)

# --------------------------------------------------
# Financial institutions
# --------------------------------------------------
Component.get_item('금융지주', namelist = ['KB금융', '신한지주', '하나금융지주', '우리금융지주', 'BNK금융지주', 'iM금융지주', 'JB금융지주', '기업은행', '제주은행', '카카오뱅크'])
Component.get_item('증권사', namelist=['미래에셋증권', '한국금융지주', 'NH투자증권', '삼성증권', '키움증권', '대신증권', '한화투자증권', '유안타증권', '교보증권', '현대차증권', '신영증권', '유진투자증권', '부국증권', '한양증권', 'SK증권', 'DB증권', '다올투자증권', '상상인증권'])


# --------------------------------------------------
# AIDC
# --------------------------------------------------
Component.get_item('AIDC 커패시터', namelist = ['LS머트리얼즈', '비나텍'])
Component.get_item('버스덕트', namelist = ['가온전선'])
Component.get_item('광증폭기', namelist = ['라이콤'])
Component.get_item('광케이블', namelist = ['대한광통신'])
Component.get_item('ESS 냉각시스템', namelist = ['한중엔시에스'])
# Component.get_item('산업용 열교환기', namelist = ['디티에스']) # 상장예정

vs = ValueChain.get_item(
    key="AIDC", 
    component_keys=['AIDC 커패시터', '버스덕트', '광증폭기', '광케이블', 'ESS 냉각시스템'],
)

# --------------------------------------------------
# Bio
# --------------------------------------------------
Component.get_item('메디컬 에스테틱', namelist = ['휴젤', '파마리서치', '메디톡스', '휴메딕스', '제테마', '녹십자웰빙']) # 미용 의료 시술 소재
Component.get_item('에스테틱 의료기기', namelist = ['클래시스', '원텍'])
Component.get_item('바이오시밀러', namelist=['셀트리온', '삼성에피스홀딩스'])
Component.get_item('바이오의약품 위탁생산', namelist=['삼성바이오로직스']) # CDMO
Component.get_item('화장품 ODM', namelist=['코스맥스', '한국콜마'])

vs = ValueChain.get_item(
    key='메디컬 바이오', 
    component_keys=['메디컬 에스테틱', '에스테틱 의료기기', '바이오시밀러', '바이오의약품 위탁생산', '화장품 ODM'], 
)

# --------------------------------------------------
# 뷰티
# --------------------------------------------------
Component.get_item('화장품 용기 제조', namelist=['펌텍코리아'])

# ==================================================
# '''