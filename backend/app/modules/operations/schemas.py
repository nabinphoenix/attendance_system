from datetime import datetime
from pydantic import BaseModel
class ImportError(BaseModel):row_number:int;error_message:str
class ImportJobRead(BaseModel):id:int;file_name:str;upload_type:str;total_rows:int;success_count:int;failed_count:int;errors:list[ImportError];created_at:datetime
