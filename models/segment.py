from build.tools.settings import PROFILES_DIR
from build.tools.analysis_tools import get_id
from build.models.json_models import JsonModel, InfoSection

class FinancialsAdjuster(InfoSection):

    ###_ segment_adjust needs update
    # PER: float | None = None 
    marcap_share: float | None = None
    revenue_share: float | None = None
    # opmargin: float | None = None
    opincome_share: float | None = None

class Segment(JsonModel):
    DIR = PROFILES_DIR
    info_section: FinancialsAdjuster

    id: str
    segment_name: str

    def get_endkey_list(self) -> list:
        return [self.key]

    def _get_subitems(self):
        pass

    def _update(self, **kwargs) -> bool:
        changed = False
        segment_name = kwargs.get('segment_name')
        if segment_name: 
            if self.segment_name != segment_name:
                self.segment_name = segment_name
                changed = True
            
        revenue_share = kwargs.get('revenue_share')
        if revenue_share: 
            financial_adjuster = FinancialsAdjuster(marcap_share=revenue_share, revenue_share=revenue_share, opincome_share=revenue_share)
            if self.info_section != financial_adjuster:
                self.info_section = financial_adjuster
                changed = True

        return changed

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs) -> JsonModel:
        segment_name = kwargs.get('segment_name')
        if not segment_name: 
            raise ValueError(f"Segment {key} cannot be initiated without name")
        revenue_share = kwargs.get('revenue_share')
        if not revenue_share: 
            raise ValueError(f"Segment {key} cannot be initiated without financials_adjuster parameters")

        filename = f"{key}_{segment_name}"
        info_section = isection if isection else FinancialsAdjuster(marcap_share=revenue_share, revenue_share=revenue_share, opincome_share=revenue_share)
        code, id = get_id(key)

        segment = Segment(
            key = key, 
            filename = filename,
            info_section = info_section, 
            id = id,
            segment_name = segment_name,
        )

        return segment
