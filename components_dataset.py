from build.models.component import ComponentManager
from build.models.profile import ProfileManager

cm = ComponentManager()
cm.get_item('Memory', namelist = ['하이닉스', '삼성전자'])
cm.get_item('Appliances', namelist = ['삼성전자', 'LG전자'])
cm.get_item('Smart_glass', namelist = ['사피엔'])
cm.get_item('Camera_module', namelist = ['LG이노텍', '삼성전기', '엠씨넥스', '세코닉스'])
cm.get_item('PCB', namelist = ['LG이노텍', '삼성전기', '엠씨넥스', '세코닉스']) # PCB, FPCB
cm.get_item('MLCC', namelist = ['삼성전기', '삼화콘덴서'])
cm.get_item('Display', namelist = ['덕산네오룩스', '이녹스첨단소재', '피엔에이치테크', 'PI첨단소재', 'LX세미콘'])
cm.get_item('Folderable', namelist = ['KH바텍', '세경하이테크', '파인엠텍'])

pm = ProfileManager()
component_list = cm.get_itemlist()
for component in component_list:
    pm.batch_process(component.get_codelist())
