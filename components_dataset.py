#%%
from scraper.component_manager import ComponentManager

cm = ComponentManager()
print(cm._items)
# cm.get_item('Mem', namelist = ['하이닉스', '삼성전자'])
cm.get_item('Folderable', namelist = ['하이닉스', '삼성전자'])
cm.get_item('Smart_Glass', namelist = ['사피엔'])
#%% 


Component(
    name='Memory', # DRAM, NAND, HBM
    companies=[
        cn('하이닉스'), 
        cn('삼성전자'), 
    ],
).to_cvm(cvm)

Component(
    name='Appliances', # 가전
    companies=[
        cn('삼성전자'), 
        cn('LG전자'), 
    ],
).to_cvm(cvm)

Component(
    name='Smart Glass', 
    companies=[
        cn('사피엔반도체'), 
    ],
).to_cvm(cvm)

Component(
    name='Camera Module', 
    companies=[
        cn('LG이노텍'), 
        cn('삼성전기'), 
        cn('엠씨넥스'), 
        cn('세코닉스'), 
    ],
).to_cvm(cvm)

Component(
    name='PCB', # PCB, FPCB
    companies=[
        cn('대덕전자'),
        cn('코리아써키트'),
        cn('심텍'), 
        cn('티엘비'),
        cn('해성디에스'),
        cn('이수페타시스'),
        cn('비에이치'),
    ],
).to_cvm(cvm)

Component(
    name='MLCC', 
    companies=[
        cn('삼성전기'),
        cn('삼화콘덴서'),
    ],
).to_cvm(cvm)

Component(
    name='Display', 
    companies=[
        cn('덕산네오룩스'),
        cn('이녹스첨단소재'),
        cn('피엔에이치테크'),
        cn('PI첨단소재'),
        cn('LX세미콘'),
    ],
).to_cvm(cvm)

Component(
    name='Folderable', 
    companies=[
        cn('KH바텍'),
        cn('세경하이테크'),
        cn('파인엠텍'),
    ],
).to_cvm(cvm)