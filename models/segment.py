from build.tools.settings import PROFILES_DIR
from build.tools.analysis_tools import get_id
from build.models.json_models import JsonModel, InfoSection

class FinancialsAdjuster(InfoSection):
    ###_ logic should be developed carefully
    # PER: float | None = None 
    marcap_share: float | None = None
    revenue_share: float | None = None
    # opmargin: float | None = None
    opincome_share: float | None = None

class Segment(JsonModel):
    DIR = PROFILES_DIR
    info_section_class = FinancialsAdjuster

    id: str
    segment_name: str

    def _update(self, **kwargs) -> bool:
        ###_ refine logic here required
        segment_name = kwargs.get('segment_name')
        revenue_share = kwargs.get('revenue_share')

        self.info_section = FinancialsAdjuster(marcap_share=revenue_share, revenue_share=revenue_share, opincome_share=revenue_share)
        self.segment_name = segment_name

        return False

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs) -> JsonModel:
        ###_ refine logic here required
        filename = f"{key}_{segment_name}"
        revenue_share = kwargs.get('revenue_share')
        info_section = isection if isection else FinancialsAdjuster(marcap_share=revenue_share, revenue_share=revenue_share, opincome_share=revenue_share)
        code, id = get_id(key)
        segment_name = kwargs.get('segment_name')

        segment = Segment(
            key = key, 
            filename = filename,
            info_section = info_section, 
            id = id,
            segment_name = segment_name,
        )

        return segment
