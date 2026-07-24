from pydantic import BaseModel

class Meta(BaseModel):
    industry: str
    scope: str
    last_updated: str

class Company(BaseModel):
    code: str
    name: str

class Product(BaseModel):
    companies: dict[str, Company]

class ValueChain(BaseModel):
    meta: Meta
    components: dict[str, Product]
    products: dict[str, Product]
    downstream: dict[str, Product]
    notes: dict
