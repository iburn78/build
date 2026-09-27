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
        return []

    def _get_subitems_and_cleanup(self):
        pass

    def _update(self, **kwargs) -> bool:
        segment_name = kwargs.get('segment_name')
        revenue_share = kwargs.get('revenue_share')
        financial_adjuster = FinancialsAdjuster(marcap_share=revenue_share, revenue_share=revenue_share, opincome_share=revenue_share)

        if (
            self.segment_name == segment_name and
            self.info_section == financial_adjuster
        ): 
            return False
        else: 
            self.segment_name = segment_name 
            self.info_section = financial_adjuster
            return True

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs) -> JsonModel:

        ###_ segment_adjust needs update
        segment_name = kwargs.get('segment_name')
        revenue_share = kwargs.get('revenue_share')

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
