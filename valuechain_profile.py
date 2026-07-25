from pydantic import BaseModel

class Company(BaseModel):
    code: str
    name: str

class Component(BaseModel):
    companies: dict[str, Company]

class ValueChainProfile(BaseModel):
    industry: str # the same as file name (unique)
    updated: str 

    components: dict[str, Component]

c1 = Company(code='1', name='c1')
c2 = Company(code='2', name='c2')
c3 = Company(code='3', name='c3')

p1 = Component(companies={'c1': c1, 'c2': c2})
p2 = Component(companies={'c2': c2, 'c3': c3})

vc1 = ValueChainProfile(industry='aero', updated='--', components={'p1': p1, 'p2':p2})

print(vc1.model_dump_json(indent=2))