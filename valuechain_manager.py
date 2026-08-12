from pydantic import BaseModel, Field
from scraper.tools.json_models import JsonModel, JsonModelManager
from scraper.tools.tools import VALUECHAIN_DIR

###_ should be customized  // change names too
class Traits(BaseModel):
    ###_ change to valuechain
    competition: str = "" # m/s, leader, competitive advatages
    key_drivers: str = "" # what drives the growth and determines who wins, technology innovation, demand growth, etc
    notes: str = "" 

class ValueChain(JsonModel): 
    DIR = VALUECHAIN_DIR
    components: list ###_ include components
    traits: Traits = Field(default_factory=Traits)
    financials: dict | None = None

    def to_cvm(self, cvm): # CV_Manager
        cvm.add_valuechain(self)

###_
class ComponentManager(JsonModelManager):
    pass