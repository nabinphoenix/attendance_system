from datetime import datetime
from pydantic import BaseModel,ConfigDict
class ImportError(BaseModel):row_number:int;error_message:str;field:str|None=None;status:str="invalid"
class ImportJobRead(BaseModel):id:int;file_name:str;upload_type:str;total_rows:int;success_count:int;failed_count:int;pending_section_references:int=0;errors:list[ImportError];created_at:datetime
class NotificationRead(BaseModel):model_config=ConfigDict(from_attributes=True);id:int;recipient_type:str;recipient_id:int;channel:str;subject:str;body:str;status:str;related_entity:str|None;related_entity_id:int|None;created_at:datetime;sent_at:datetime|None
class AuditRead(BaseModel):id:int;actor_id:int;actor_name:str;action:str;entity_type:str;entity_id:int;details:str;created_at:datetime
class AuditPage(BaseModel):items:list[AuditRead];total:int;page:int;page_size:int
