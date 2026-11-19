"""Validate customer fulfillment details before creating an order or charge."""
from pydantic import BaseModel,EmailStr,Field,ValidationError
import re

class CheckoutContact(BaseModel):
    name:str=Field(min_length=1,max_length=160)
    email:EmailStr
    phone:str=Field(min_length=7,max_length=30,pattern=r'^[+0-9 ()-]+$')
    address:str=Field(default="",max_length=1000)

def contact_for_checkout(raw,fulfillment):
    try:
        contact=CheckoutContact.model_validate(raw or {})
        data=contact.model_dump(mode="json")
        data={key:value.strip() for key,value in data.items()}
        if not data["name"] or not 7<=len(re.sub(r'\D','',data["phone"]))<=15 or (fulfillment=="delivery" and len(data["address"])<5):raise ValueError()
        return data
    except (ValidationError,ValueError):
        raise ValueError("checkout_contact_required") from None
