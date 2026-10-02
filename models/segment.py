from build.tools.settings import PROFILES_DIR, sanitized_filename, get_id
from build.models.json_model import JsonModel, InfoSection
from build.analysis.sector_analysis import FinancialsData, SectorAnalysis

class FinancialsAdjuster(InfoSection):
    revenue_share: float | None = None
    PER: float | None = None
    opmargin: float | None = None

class Segment(JsonModel):
    DIR = PROFILES_DIR
    info_section: FinancialsAdjuster

    id: str
    profile_name: str
    profile_code: str
    segment_name: str

    def _get_name(self):
        return f"{self.profile_name}({self.id})"

    def _get_subitems(self):
        pass

    def _get_financials(self, **kwargs):
        _sa = SectorAnalysis()
        _sa.meta['name'] = self.profile_name
        _sa.meta['code'] = self.profile_code
        _sa.meta['id'] = self.id
        _sa.meta['segment_name'] = self.segment_name
        _sa.adjuster = self.info_section

        fd_list = [FinancialsData(key=self.key, adjuster=self.info_section)]
        _sa.process(fd_list,
                    subitems_financials=self._get_subitems_financials(),
                    plot_path=self.get_json_path().with_suffix('.png'))
        self.financials = _sa.financials
        self._subitems_financials_processed = _sa._subitems_financials_processed

    def _update(self, **kwargs) -> bool:
        changed = False
        segment_name = kwargs.get('segment_name')
        _info_section = kwargs.get('info_section')
        if segment_name:
            if self.segment_name != segment_name:
                self.segment_name = segment_name
                self.filename = sanitized_filename(f"{self.key}_{segment_name}")
                changed = True

        revenue_share = kwargs.get('revenue_share')
        if revenue_share:
            if self.info_section.revenue_share != revenue_share and self.info_section.reviewed:
                raise ValueError(f"Segment {self.key} reviewed revenue_share mismatches the profile's data")

            # not-reviewed data set back to default
            if not self.info_section.reviewed and not _info_section:
                financial_adjuster = FinancialsAdjuster(revenue_share=revenue_share)
                if self.info_section != financial_adjuster:
                    self.info_section = financial_adjuster

        if _info_section:
            self.info_section = _info_section
            changed = True

        # check financials after checking FinancialsAdjuster
        if changed or self._update_financials(**kwargs):
            self._get_financials(**kwargs)
            changed = True

        return changed

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs) -> JsonModel:
        code, id = get_id(key)
        profile_name = kwargs.get('profile_name')
        segment_name = kwargs.get('segment_name')
        if not profile_name or not segment_name:
            raise ValueError(f"Segment {key} cannot be initiated without names")
        revenue_share = kwargs.get('revenue_share')
        if revenue_share is None:
            raise ValueError(f"Segment {key} cannot be initiated without financials_adjuster parameters")

        filename = f"{key}_{segment_name}"
        info_section = isection if isection else FinancialsAdjuster(revenue_share=revenue_share)

        segment = Segment(
            key = key,
            filename = filename,
            info_section = info_section,
            id = id,
            profile_name = profile_name,
            profile_code = code,
            segment_name = segment_name,
        )

        # financials is filled after segment creation
        segment._get_financials(**kwargs)

        return segment
