from build.tools.settings import PROFILES_DIR
from build.tools.analysis_tools import get_id
from build.models.json_models import JsonModel, InfoSection
from pathlib import Path

class FinancialsAdjuster(InfoSection):
    ###_ logic should be developed carefully
    # PER: float | None = None 
    marcap_share: float | None = None
    revenue_share: float | None = None
    # opmargin: float | None = None
    opincome_share: float | None = None

class Segment(JsonModel):
    DIR = PROFILES_DIR
    info_section_name = 'financials_adjuster'
    info_section_class = FinancialsAdjuster

    id: str
    segment_name: str

    def assign_sub_items_keys(self):
        pass

    def get_qualitative_dict(self) -> dict:
        return {
            self.info_section_name: self.info_section,
        }

    def get_news_dir(self) -> Path | None:
        return None

    def update(self) -> bool:
        return False

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, fsection: dict | None, **kwargs) -> JsonModel:
        code, id = get_id(key)
        sg = kwargs.get('segment_name', '')
        filename = f"{key}_{sg}"

        segment = Segment(
            key = key, 
            filename=filename,
            info_section = isection if isection else FinancialsAdjuster(marcap_share=0.5, revenue_share=0.5, opincome_share=0.5), 
            financials=fsection, 
            id = id,
            segment_name=sg,
        )

        return segment
