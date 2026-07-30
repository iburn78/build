from scraper.tools.tools import Component, ValueChain, cn

# Component and ValueChain
class CV_Manager: 
    def __init__(self):
        self._components = Component.load_all()
        self._value_chains = ValueChain.load_all()

    def add_component(self, cp):
        self._components[cp.name] = cp
        cp.save_to_file()

if __name__ == "__main__":
    cvm = CV_Manager()

    cp = Component(
        name="HBM",
        companies=[
            cn('하이닉스'), cn('삼성전자'), 
        ],
        updated="",
        note=""
    )

    cvm.add_component(cp)

